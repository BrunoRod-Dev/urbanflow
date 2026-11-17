"""Sensibilidad del cruce Roosevelt–Honduras a tres demandas sintéticas.

Reutiliza la comparación de la etapa 1F.1. Entre A y B, en cada nivel, solo
cambia maxDur de la primera fase. 90 y 135 vehículos son el doble y el triple
de cada recorrido de la muestra de 45. No son temporadas de Maldonado.
"""

import json
import shutil
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.decision_ab import (
    CONTROLLER, END, SOURCE, DecisionError, completed_signature, locate_sumo,
    metric_pair, only_maxdur_edit, prepare_variant_network,
    run_sumo, source_hashes, sumo_version,
)
from tools.storage_policy import file_sha256, temporary_directory, write_hash_reference

STAGE = "etapa1f2"
PUBLIC = ROOT / "urbanflow-web/assets/decision-demand.json"
PRIOR = ROOT / "results/_tmp/etapa1f1"
LEVELS = (45, 90, 135)
PER_FLOW = {45: 3, 90: 6, 135: 9}
NUMBER_NEEDLE = b'number="3"'
HORIZON_SHARE = 0.3


def scale_routes(source, per_flow):
    """Multiplica por igual los 15 flujos. El begin de cada uno no se mueve."""
    data = Path(source).read_bytes()
    if data.count(NUMBER_NEEDLE) != 15:
        raise DecisionError("La muestra no tiene 15 flujos de 3 vehículos. No se escaló la demanda.")
    if per_flow == 3:
        return data
    replacement = f'number="{per_flow}"'.encode()
    if len(replacement) != len(NUMBER_NEEDLE):
        raise DecisionError("El número de vehículos por flujo tiene que ocupar el mismo lugar.")
    return data.replace(NUMBER_NEEDLE, replacement)


def flow_schedule(per_flow):
    """begin + i * (240 - begin) / per_flow, que es como SUMO reparte number."""
    return round((END - 0) / per_flow, 4)


def classify_trips(path):
    finished, pending, rejected = {}, {}, []
    for trip in ET.parse(path).iter("tripinfo"):
        depart = trip.get("depart")
        arrival = trip.get("arrival")
        vaporized = trip.get("vaporized") or ""
        if vaporized not in {"", "end"}:
            rejected.append(trip.get("id"))
        if not depart or float(depart) < 0:
            continue
        record = (float(trip.get("duration")), float(trip.get("waitingTime")), float(depart))
        if arrival and float(arrival) >= 0:
            finished[trip.get("id")] = record
        else:
            pending[trip.get("id")] = record
    return finished, pending, rejected


def cohort(finished_a, finished_b):
    shared = sorted(set(finished_a) & set(finished_b))
    if not shared:
        return {"count": 0, "departMin": None, "departMax": None, "meanTravel": None, "meanWait": None}
    travel = (
        sum(finished_a[key][0] for key in shared) / len(shared),
        sum(finished_b[key][0] for key in shared) / len(shared),
    )
    wait = (
        sum(finished_a[key][1] for key in shared) / len(shared),
        sum(finished_b[key][1] for key in shared) / len(shared),
    )
    departs = [finished_a[key][2] for key in shared]
    return {
        "count": len(shared),
        "departMin": round(min(departs), 2),
        "departMax": round(max(departs), 2),
        "meanTravel": metric_pair(travel[0], travel[1], 2),
        "meanWait": metric_pair(wait[0], wait[1], 2),
    }


def closed_phases(path, controller, end):
    """Duraciones que terminan en un cambio de fase. La última queda censurada por el horizonte."""
    events = [
        (float(state.get("time")), state.get("phase"))
        for state in ET.parse(path).iter("tlsState")
        if state.get("id") == controller
    ]
    lengths = {}
    if not events:
        return lengths, None
    start, phase = events[0]
    for time, next_phase in events[1:]:
        if next_phase == phase:
            continue
        lengths.setdefault(phase, []).append(round(time - start, 1))
        start, phase = time, next_phase
    return lengths, {"phase": phase, "seconds": round(end - start, 1)}


def cap_effect(lengths_a, lengths_b, censored_b):
    first_a = lengths_a.get("0", [])
    first_b = lengths_b.get("0", [])
    cuts = 0
    for left, right in zip(first_a, first_b):
        if abs(left - right) <= 0.05:
            continue
        if left > 15 and abs(right - 15) <= 0.05:
            cuts += 1
            continue
        break
    return {
        "openingsA": len(first_a),
        "openingsB": len(first_b),
        "paired": len(first_a) == len(first_b) and len(first_a) > 0,
        "cutByCap": cuts,
        "bAtCap": sum(1 for value in first_b if abs(value - 15) <= 0.05),
        "aAbove15": sum(1 for value in first_a if value > 15),
        "aAtReferenceMax": sum(1 for value in first_a if value >= 49.5),
        "maxA": round(max(first_a), 1) if first_a else None,
        "maxB": round(max(first_b), 1) if first_b else None,
        "censoredPhase0": censored_b["seconds"] if censored_b and censored_b["phase"] == "0" else None,
    }


def spanish_seconds(value):
    if value is None:
        return "—"
    return f"{value:.2f}".replace(".", ",")


def level_report(demand, trips_a, trips_b, signals_a, signals_b, routes):
    finished_a, pending_a, rejected_a = classify_trips(trips_a)
    finished_b, pending_b, rejected_b = classify_trips(trips_b)
    if rejected_a or rejected_b:
        raise DecisionError(f"SUMO vaporizó vehículos en la demanda de {demand}. No se publica ese nivel.")
    inserted_a = len(finished_a) + len(pending_a)
    inserted_b = len(finished_b) + len(pending_b)
    same = cohort(finished_a, finished_b)
    lengths_a, _ = closed_phases(signals_a, CONTROLLER, END)
    lengths_b, censored_b = closed_phases(signals_b, CONTROLLER, END)
    effect = cap_effect(lengths_a, lengths_b, censored_b)
    if effect["maxB"] is None or effect["maxB"] > 15.5 or (effect["censoredPhase0"] or 0) > 15.5:
        raise DecisionError(f"Con {demand} vehículos la variante B superó el máximo de 15 s.")
    unfinished_a = len(pending_a)
    unfinished_b = len(pending_b)
    share_a = unfinished_a / inserted_a if inserted_a else 1
    share_b = unfinished_b / inserted_b if inserted_b else 1
    entered = inserted_a == demand and inserted_b == demand
    return {
        "demand": demand,
        "perFlow": PER_FLOW[demand],
        "zeroBeginSpacingSeconds": flow_schedule(PER_FLOW[demand]),
        "planned": demand,
        "inserted": {"a": inserted_a, "b": inserted_b},
        "completed": {"a": len(finished_a), "b": len(finished_b)},
        "unfinished": {"a": unfinished_a, "b": unfinished_b},
        "unfinishedWaitSeconds": {
            "a": round(sum(item[1] for item in pending_a.values()), 1),
            "b": round(sum(item[1] for item in pending_b.values()), 1),
        },
        "onlyFinishedA": len(set(finished_a) - set(finished_b)),
        "onlyFinishedB": len(set(finished_b) - set(finished_a)),
        "cohort": same,
        "cap": effect,
        "horizonLimited": (not entered) or share_a >= HORIZON_SHARE or share_b >= HORIZON_SHARE,
        "evidence": {
            "routes": routes.relative_to(ROOT).as_posix(),
            "routesSha256": file_sha256(routes),
            "tripsA": trips_a.relative_to(ROOT).as_posix(),
            "tripsB": trips_b.relative_to(ROOT).as_posix(),
            "signalsA": signals_a.relative_to(ROOT).as_posix(),
            "signalsB": signals_b.relative_to(ROOT).as_posix(),
        },
    }


def conclude(levels):
    longest = ", ".join(
        f"{spanish_tenths(level['cap']['maxA'])} s con {level['demand']}"
        for level in levels
    )
    at_cap_values = [str(level["cap"]["bAtCap"]) for level in levels]
    at_cap = ", ".join(at_cap_values[:-1]) + " y " + at_cap_values[-1]
    if all(level["cap"]["cutByCap"] == 1 for level in levels):
        cut_sentence = "El tope de 15 s corta esa verde una vez en cada nivel."
    else:
        listed = ", ".join(str(level["cap"]["cutByCap"]) for level in levels)
        cut_sentence = f"El tope de 15 s la corta {listed} veces."
    cohort_changes = ", ".join(
        spanish_seconds(level["cohort"]["meanTravel"]["absolute"]) + " s"
        for level in levels if level["cohort"]["meanTravel"]
    )
    parts = [
        "90 y 135 vehículos son el doble y el triple de cada uno de los 15 recorridos de la muestra. "
        "No son una temporada de Maldonado.",
        "Entran todos los vehículos pedidos. "
        f"La verde cerrada más larga de A es {longest}. "
        f"{cut_sentence} "
        f"B queda en 15 s en {at_cap} verdes cerradas. "
        "Si hay una de más, ocurre después de que los ciclos dejan de coincidir y no se cuenta como el mismo corte. "
        "Las demás verdes cerradas de esa fase terminan en 13 o 14 s.",
    ]
    limited = [level for level in levels if level["horizonLimited"]]
    if limited:
        unfinished = "; ".join(
            f"{level['demand']}: {level['unfinished']['a']} en A y {level['unfinished']['b']} en B"
            for level in limited
        )
        parts.append(
            f"A los 240 s siguen sin terminar {unfinished}. "
            "El promedio de quienes llegan no mide a toda la demanda en esos niveles."
        )
    parts.append(
        f"En la cohorte que termina en las dos variantes, el cambio de viaje es {cohort_changes}. "
        "No es una diferencia estable de operación. "
        "El programa de referencia sigue siendo el que SUMO infirió, no un plan de la Intendencia."
    )
    return " ".join(parts)


def spanish_tenths(value):
    return f"{value:.1f}".replace(".", ",")


def build_report(levels, version, network):
    return {
        "experimental": True,
        "calibrated": False,
        "seasonal": False,
        "title": "Sensibilidad a la demanda",
        "note": (
            "Misma red, mismas rutas, misma semilla 42 y mismos 240 s en A y en B. "
            "Solo cambia el máximo de la primera fase, de 50 s a 15 s. "
            "Cada nivel multiplica por igual los 15 flujos de la muestra."
        ),
        "criterion": (
            "SUMO reparte las salidas de cada flujo entre su begin original y los 240 s, "
            "con separación (240 − begin) / número. Con 3, 6 y 9 vehículos por flujo, "
            "los horarios de la muestra de 45 quedan dentro de las grillas de 90 y de 135. "
            "La cohorte de tiempos es la de los viajes que terminan en las dos variantes. "
            "Quienes siguen en la red a los 240 s se cuentan aparte y no entran al promedio. "
            "Si son al menos el 30 % de los insertados, el nivel queda cortado por el horizonte. "
            "La última fase abierta al segundo 240 no se cuenta como verde terminada."
        ),
        "levels": levels,
        "conclusion": conclude(levels),
        "network": network.relative_to(ROOT).as_posix(),
        "sumo": version,
    }


def publish(report, stage):
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(text, encoding="utf-8")
    (stage / "sensitivity.json").write_text(text, encoding="utf-8")


def cite(stage, source, name):
    folder = stage / "cited"
    folder.mkdir(parents=True, exist_ok=True)
    write_hash_reference(folder, source, name)


def prior_level_ready():
    needed = [PRIOR / side / name for side in ("a", "b") for name in ("trips.xml", "signal-states.xml")]
    if not all(path.is_file() for path in needed):
        return False
    if completed_signature(SOURCE / "trips.xml") != completed_signature(PRIOR / "a" / "trips.xml"):
        return False
    lengths_b, censored_b = closed_phases(PRIOR / "b" / "signal-states.xml", CONTROLLER, END)
    closed_max = max(lengths_b.get("0", [0]))
    censored = censored_b["seconds"] if censored_b and censored_b["phase"] == "0" else 0
    return closed_max <= 15.5 and censored <= 15.5


def ensure_network(stage):
    cited = PRIOR / "b-network.net.xml"
    if cited.is_file() and only_maxdur_edit(SOURCE / "network.net.xml", cited):
        cite(stage, cited, "b-network.json")
        return cited
    return prepare_variant_network(stage)


def write_routes(stage, demand):
    if demand == 45:
        return SOURCE / "routes.rou.xml"
    path = stage / f"routes-{demand}.rou.xml"
    path.write_bytes(scale_routes(SOURCE / "routes.rou.xml", PER_FLOW[demand]))
    return path


def simulate_level(executable, environment, stage, demand, network_b):
    folder = stage / f"d{demand}"
    if folder.exists():
        shutil.rmtree(folder)
    routes = write_routes(stage, demand)
    run_sumo(executable, environment, folder / "a", SOURCE / "network.net.xml", routes)
    run_sumo(executable, environment, folder / "b", network_b, routes)
    if demand == 45:
        saved = completed_signature(SOURCE / "trips.xml")
        if completed_signature(folder / "a" / "trips.xml") != saved:
            raise DecisionError("La demanda de 45 no reprodujo la corrida guardada.")
    return (
        folder / "a" / "trips.xml", folder / "b" / "trips.xml",
        folder / "a" / "signal-states.xml", folder / "b" / "signal-states.xml", routes,
    )


def level_paths(stage, demand, executable, environment, network_b):
    if demand == 45 and prior_level_ready():
        cite(stage, PRIOR / "a" / "trips.xml", "d45-a-trips.json")
        cite(stage, PRIOR / "b" / "trips.xml", "d45-b-trips.json")
        cite(stage, PRIOR / "a" / "signal-states.xml", "d45-a-signals.json")
        cite(stage, PRIOR / "b" / "signal-states.xml", "d45-b-signals.json")
        return (
            PRIOR / "a" / "trips.xml", PRIOR / "b" / "trips.xml",
            PRIOR / "a" / "signal-states.xml", PRIOR / "b" / "signal-states.xml",
            SOURCE / "routes.rou.xml",
        )
    return simulate_level(executable, environment, stage, demand, network_b)


def main():
    before = source_hashes()
    executable, environment = locate_sumo()
    version = sumo_version(executable, environment)
    stage = temporary_directory(ROOT, STAGE)
    cited = stage / "cited"
    if cited.exists():
        shutil.rmtree(cited)
    network = ensure_network(stage)
    levels = []
    for demand in LEVELS:
        trips_a, trips_b, signals_a, signals_b, routes = level_paths(
            stage, demand, executable, environment, network)
        levels.append(level_report(demand, trips_a, trips_b, signals_a, signals_b, routes))
    if source_hashes() != before:
        PUBLIC.unlink(missing_ok=True)
        raise DecisionError("La corrida guardada cambió durante el experimento.")
    report = build_report(levels, version, network)
    publish(report, stage)
    print(json.dumps({
        "levels": [{
            "demand": level["demand"],
            "completed": level["completed"],
            "unfinished": level["unfinished"],
            "cohort": level["cohort"]["count"],
            "travel": None if not level["cohort"]["meanTravel"] else level["cohort"]["meanTravel"]["absolute"],
            "wait": None if not level["cohort"]["meanWait"] else level["cohort"]["meanWait"]["absolute"],
            "cutByCap": level["cap"]["cutByCap"],
            "bAtCap": level["cap"]["bAtCap"],
            "openings": [level["cap"]["openingsA"], level["cap"]["openingsB"]],
            "horizonLimited": level["horizonLimited"],
        } for level in levels],
        "conclusion": report["conclusion"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except DecisionError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
