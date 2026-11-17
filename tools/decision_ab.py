"""Comparación A/B de un parámetro semafórico en la corrida guardada de Roosevelt.

A reutiliza la red y las rutas ya simuladas. B recibe una copia temporal donde
solo cambia maxDur de la primera fase de Roosevelt y Honduras. Ninguna salida
se escribe en la corrida guardada ni en la candidata certificada.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.storage_policy import file_sha256, temporary_directory

SOURCE = ROOT / "results/studies/c44da2efd14c48569d6a9ce276916ba5"
CONTROLLER = "joinedS_1360014840_13966777057_13966777058_2375592994"
PHASE_STATE = "GGGrrrrGGGrrrGGGGrrGGG"
REFERENCE_MAX = "50"
VARIANT_MAX = "15"
NEEDLE = f'<phase duration="39" state="{PHASE_STATE}" minDur="13" maxDur="{REFERENCE_MAX}"/>'.encode()
REPLACEMENT = f'<phase duration="39" state="{PHASE_STATE}" minDur="13" maxDur="{VARIANT_MAX}"/>'.encode()
END = 240
SEED = 42
STEP = "0.5"
STAGE = "etapa1f1"
PUBLIC = ROOT / "urbanflow-web/assets/decision-roosevelt.json"
SOURCE_FILES = ("network.net.xml", "routes.rou.xml", "trips.xml", "replay.json", "trajectories.xml", "summary.xml")


class DecisionError(RuntimeError):
    """La comparación no se puede publicar con estos archivos."""


def measure_trips(path):
    """Promedios de los viajes que llegan. Los que siguen al cierre no entran al promedio."""
    durations = []
    waits = []
    inserted = 0
    for trip in ET.parse(path).iter("tripinfo"):
        inserted += 1
        arrival = trip.get("arrival")
        if not arrival or float(arrival) < 0:
            continue
        durations.append(float(trip.get("duration")))
        waits.append(float(trip.get("waitingTime")))
    completed = len(durations)
    return {
        "inserted": inserted,
        "completed": completed,
        "meanTravel": sum(durations) / completed if completed else None,
        "meanWait": sum(waits) / completed if completed else None,
    }


def completed_signature(path):
    rows = {}
    for trip in ET.parse(path).iter("tripinfo"):
        arrival = trip.get("arrival")
        if not arrival or float(arrival) < 0:
            continue
        rows[trip.get("id")] = (trip.get("duration"), trip.get("waitingTime"), arrival)
    return rows


def phase_lengths(path, controller, end):
    """Une muestras seguidas de la misma fase. SUMO puede registrar cada paso."""
    events = [
        (float(state.get("time")), state.get("phase"))
        for state in ET.parse(path).iter("tlsState")
        if state.get("id") == controller
    ]
    lengths = {}
    if not events:
        return lengths
    start, phase = events[0]
    for time, next_phase in events[1:]:
        if next_phase == phase:
            continue
        lengths.setdefault(phase, []).append(round(time - start, 1))
        start, phase = time, next_phase
    lengths.setdefault(phase, []).append(round(end - start, 1))
    return lengths


def metric_pair(left, right, digits):
    if left is None or right is None:
        return {"a": left, "b": right, "absolute": None, "percent": None}
    if digits is None:
        absolute = right - left
        percent = None if left == 0 else round(absolute / left * 100, 1)
        return {"a": left, "b": right, "absolute": absolute, "percent": percent}
    rounded_left = round(left, digits)
    rounded_right = round(right, digits)
    absolute = round(rounded_right - rounded_left, digits)
    percent = None if rounded_left == 0 else round(absolute / rounded_left * 100, 1)
    return {"a": rounded_left, "b": rounded_right, "absolute": absolute, "percent": percent}


def only_maxdur_edit(original, copy):
    left = Path(original).read_bytes()
    right = Path(copy).read_bytes()
    if len(left) != len(right):
        return False
    diffs = [index for index, (before, after) in enumerate(zip(left, right)) if before != after]
    if len(diffs) != 2 or diffs[1] != diffs[0] + 1:
        return False
    start = diffs[0]
    return left[start:start + 2] == REFERENCE_MAX.encode() and right[start:start + 2] == VARIANT_MAX.encode()


def locate_sumo():
    portable = ROOT / "results/baseline-v001-tools/portable/sumo-1.26.0"
    executable = portable / "bin/sumo.exe"
    if not executable.is_file():
        raise DecisionError("No está el SUMO portable 1.26.0. No se instaló otro.")
    environment = os.environ.copy()
    environment["SUMO_HOME"] = str(portable)
    return str(executable), environment


def sumo_version(executable, environment):
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, env=environment, timeout=30)
    line = next((item.strip() for item in (result.stdout + result.stderr).splitlines() if item.strip()), "")
    return line


def write_signal_probe(path):
    path.write_text(
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<additional><timedEvent type=\"SaveTLSStates\" dest=\"signal-states.xml\"/></additional>\n",
        encoding="utf-8",
    )


def run_sumo(executable, environment, directory, network, routes):
    directory.mkdir(parents=True, exist_ok=True)
    additional = directory / "signals-probe.add.xml"
    write_signal_probe(additional)
    command = [
        executable, "--net-file", str(network), "--route-files", str(routes),
        "--additional-files", str(additional), "--end", str(END), "--step-length", STEP,
        "--seed", str(SEED), "--time-to-teleport", "-1", "--no-step-log", "true",
        "--tripinfo-output", "trips.xml", "--tripinfo-output.write-unfinished", "true",
    ]
    result = subprocess.run(command, cwd=directory, env=environment, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=180)
    (directory / "sumo.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise DecisionError(f"SUMO terminó con código {result.returncode}. El detalle está en {directory / 'sumo.log'}.")
    if not (directory / "trips.xml").is_file() or not (directory / "signal-states.xml").is_file():
        raise DecisionError(f"SUMO no escribió viajes y estados semafóricos en {directory}.")


def source_hashes():
    return {name: file_sha256(SOURCE / name) for name in SOURCE_FILES}


def paired_trips(path_a, path_b):
    def finished(path):
        rows = {}
        for trip in ET.parse(path).iter("tripinfo"):
            arrival = trip.get("arrival")
            if not arrival or float(arrival) < 0:
                continue
            rows[trip.get("id")] = (float(trip.get("duration")), float(trip.get("waitingTime")))
        return rows

    left, right = finished(path_a), finished(path_b)
    shared = sorted(set(left) & set(right))
    only_b = sorted(set(right) - set(left))
    return {
        "count": len(shared),
        "onlyA": sorted(set(left) - set(right)),
        "onlyB": [{"id": key, "duration": right[key][0], "waitingTime": right[key][1]} for key in only_b],
        "meanTravel": None if not shared else (
            sum(left[key][0] for key in shared) / len(shared),
            sum(right[key][0] for key in shared) / len(shared),
        ),
        "meanWait": None if not shared else (
            sum(left[key][1] for key in shared) / len(shared),
            sum(right[key][1] for key in shared) / len(shared),
        ),
    }


def spanish_seconds(value):
    return f"{value:.2f}".replace(".", ",")


def spanish_tenths(value):
    return f"{value:.1f}".replace(".", ",")


def limitation_text(metrics, phases, paired):
    lengths_a = phases["a"].get("0", [])
    lengths_b = phases["b"].get("0", [])
    max_a = max(lengths_a) if lengths_a else 0
    max_b = max(lengths_b) if lengths_b else 0
    held_at_minimum = sum(left == 13 and right == 13 for left, right in zip(lengths_a, lengths_b))
    parts = [
        f"La primera fase se abrió {len(lengths_a)} veces en A y {len(lengths_b)} veces en B. "
        f"En {held_at_minimum} de esas aperturas las dos la cortaron a los 13 s, el mínimo guardado. "
        f"El máximo fue {spanish_tenths(max_a)} s en A y {spanish_tenths(max_b)} s en B.",
    ]
    travel = abs(metrics["meanTravelSame"]["absolute"] or 0)
    wait = abs(metrics["meanWaitSame"]["absolute"] or 0)
    if travel < 1 and wait < 1:
        same = (
            f"Los {paired['count']} vehículos que llegan en las dos corridas cambian "
            f"{spanish_seconds(metrics['meanTravelSame']['absolute'])} s el viaje medio y "
            f"{spanish_seconds(metrics['meanWaitSame']['absolute'])} s la espera."
        )
        extra = ""
        if len(paired["onlyB"]) == 1 and not paired["onlyA"]:
            trip = paired["onlyB"][0]
            extra = (
                f" B también completa el viaje {trip['id']}, de {spanish_seconds(trip['duration'])} s, "
                "que en A no llega a terminar. Por eso el promedio de todos los que llegan no coincide "
                "con el promedio de los mismos vehículos."
            )
        parts.append(same + extra)
        parts.append("La demanda de muestra, 45 autos en 4 minutos, no produce una diferencia relevante de operación.")
    else:
        parts.append("La diferencia es lo que SUMO produjo con la demanda de muestra. No pronostica el tránsito de Maldonado.")
    return " ".join(parts)


def build_report(measured, phases, paired, version, hashes):
    same_count = paired["count"]
    metrics = {
        "meanTravel": {"label": "Tiempo medio de viaje, quienes llegaron", "unit": "s", "decimals": 2,
                       **metric_pair(measured["a"]["meanTravel"], measured["b"]["meanTravel"], 2)},
        "meanWait": {"label": "Tiempo medio de espera, quienes llegaron", "unit": "s", "decimals": 2,
                     **metric_pair(measured["a"]["meanWait"], measured["b"]["meanWait"], 2)},
        "meanTravelSame": {"label": f"Tiempo medio de viaje, mismos {same_count} vehículos", "unit": "s", "decimals": 2,
                           **metric_pair(paired["meanTravel"][0], paired["meanTravel"][1], 2)},
        "meanWaitSame": {"label": f"Tiempo medio de espera, mismos {same_count} vehículos", "unit": "s", "decimals": 2,
                         **metric_pair(paired["meanWait"][0], paired["meanWait"][1], 2)},
        "completed": {"label": "Vehículos que completaron", "unit": "", "decimals": None,
                      **metric_pair(measured["a"]["completed"], measured["b"]["completed"], None)},
        "inserted": {"label": "Vehículos insertados", "unit": "", "decimals": None,
                     **metric_pair(measured["a"]["inserted"], measured["b"]["inserted"], None)},
    }
    max_a = max(phases["a"].get("0", [0]))
    max_b = max(phases["b"].get("0", [0]))
    return {
        "experimental": True,
        "calibrated": False,
        "title": "Comparación experimental",
        "intro": "Roosevelt y Honduras, dentro de la corrida guardada de la rotonda. Misma red, misma demanda, un parámetro semafórico distinto.",
        "notice": "Escenario experimental. No está calibrado con conteos reales de Maldonado ni con el plan semafórico de la Intendencia.",
        "variants": {
            "a": {"label": "A · Referencia", "detail": "Programa guardado. Primera fase: duración 39 s, mínimo 13 s, máximo 50 s."},
            "b": {"label": "B · Máximo de 15 s", "detail": "Solo el máximo de esa fase pasa de 50 s a 15 s. Duración nominal, mínimo y estado quedan igual."},
        },
        "metrics": metrics,
        "queues": {
            "measured": False,
            "note": "No hay cola en metros. En este proyecto esa medida sale de la trayectoria completa, y esta comparación no vuelve a guardarla.",
        },
        "phase0MaxSeconds": {"a": round(max_a, 1), "b": round(max_b, 1)},
        "limitation": limitation_text(metrics, phases, paired),
        "method": [
            "Las dos corridas usan la red, las rutas, la demanda de 45 autos, la semilla 42, el paso de 0,5 s y los 240 s de la corrida guardada de la rotonda de Roosevelt y Camacho. Esa corrida incluye el cruce semaforizado de Roosevelt y Honduras. La demo esquemática de la rotonda no tiene semáforos.",
            f"A lee network.net.xml de esa corrida, sin modificarlo. B usa una copia temporal en la que el único cambio es maxDur de la primera fase de {CONTROLLER}: de {REFERENCE_MAX} s a {VARIANT_MAX} s. El estado de la fase sigue siendo {PHASE_STATE}. Los demás controladores no cambian.",
            "Ese programa lo armó SUMO al construir la red. No es un plan de la Intendencia de Maldonado.",
            "El tiempo de viaje y la espera salen de trips.xml. La espera es el waitingTime de SUMO, el tiempo por debajo de 0,1 m/s. El promedio usa solo los vehículos que llegan.",
            f"En A la primera fase llegó a {spanish_tenths(max_a)} s. En B llegó a {spanish_tenths(max_b)} s.",
            f"{version}. Las salidas están en results/_tmp/etapa1f1 y no reemplazan la corrida guardada.",
        ],
        "sources": {"run": "results/studies/c44da2efd14c48569d6a9ce276916ba5", "sha256": hashes},
    }


def publish(report, stage):
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(text, encoding="utf-8")
    (stage / "comparison.json").write_text(text, encoding="utf-8")


def prepare_variant_network(stage):
    original = SOURCE / "network.net.xml"
    copy = stage / "b-network.net.xml"
    data = original.read_bytes()
    if data.count(NEEDLE) != 1:
        raise DecisionError("La fase de referencia no está una sola vez en la red guardada. No se armó la variante B.")
    copy.write_bytes(data.replace(NEEDLE, REPLACEMENT, 1))
    if not only_maxdur_edit(original, copy):
        raise DecisionError("La copia de B no quedó limitada al cambio de maxDur.")
    return copy


def main():
    before = source_hashes()
    executable, environment = locate_sumo()
    version = sumo_version(executable, environment)
    stage = temporary_directory(ROOT, STAGE)
    for name in ("a", "b"):
        folder = stage / name
        if folder.exists():
            shutil.rmtree(folder)
    for leftover in ("signal-states.xml", "signals-probe.add.xml"):
        (stage / leftover).unlink(missing_ok=True)
    network_b = prepare_variant_network(stage)
    routes = SOURCE / "routes.rou.xml"
    run_sumo(executable, environment, stage / "a", SOURCE / "network.net.xml", routes)
    saved = completed_signature(SOURCE / "trips.xml")
    reproduced = completed_signature(stage / "a" / "trips.xml")
    if reproduced != saved:
        PUBLIC.unlink(missing_ok=True)
        mismatch = [key for key in sorted(set(saved) | set(reproduced)) if saved.get(key) != reproduced.get(key)]
        (stage / "bloqueo.json").write_text(json.dumps({
            "reason": "La variante A no reprodujo los viajes de la corrida guardada.",
            "mismatched": mismatch[:8],
            "saved": len(saved),
            "reproduced": len(reproduced),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise DecisionError("La variante A no reprodujo la corrida guardada. No se publicó la comparación.")
    run_sumo(executable, environment, stage / "b", network_b, routes)
    phases = {
        "a": phase_lengths(stage / "a" / "signal-states.xml", CONTROLLER, END),
        "b": phase_lengths(stage / "b" / "signal-states.xml", CONTROLLER, END),
    }
    max_b = max(phases["b"].get("0", [0]))
    if max_b > float(VARIANT_MAX) + 0.5:
        PUBLIC.unlink(missing_ok=True)
        raise DecisionError(f"La variante B sostuvo la primera fase {max_b:.1f} s. El máximo de {VARIANT_MAX} s no se aplicó.")
    measured = {"a": measure_trips(stage / "a" / "trips.xml"), "b": measure_trips(stage / "b" / "trips.xml")}
    paired = paired_trips(stage / "a" / "trips.xml", stage / "b" / "trips.xml")
    after = source_hashes()
    if after != before:
        PUBLIC.unlink(missing_ok=True)
        raise DecisionError("La corrida guardada cambió durante la comparación. No se publicó el resultado.")
    report = build_report(measured, phases, paired, version, before)
    publish(report, stage)
    print(json.dumps({
        "meanTravel": report["metrics"]["meanTravel"],
        "meanWait": report["metrics"]["meanWait"],
        "completed": report["metrics"]["completed"],
        "inserted": report["metrics"]["inserted"],
        "phase0MaxSeconds": report["phase0MaxSeconds"],
        "limitation": report["limitation"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except DecisionError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
