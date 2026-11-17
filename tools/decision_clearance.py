"""Separa la generación de demanda del tiempo para terminar el viaje.

Los flujos de 45, 90 y 135 vehículos siguen terminando en el segundo 240.
La simulación continúa hasta CLEARANCE_END sin agregar flujos. Entre A y B
solo cambia maxDur de la primera fase de Roosevelt y Honduras.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from statistics import median
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.decision_ab import (
    CONTROLLER, END, PHASE_STATE, SEED, SOURCE, STEP, DecisionError,
    completed_signature, locate_sumo, only_maxdur_edit,
    prepare_variant_network, source_hashes, sumo_version,
)
from tools.demand_sensitivity import PER_FLOW, cohort, scale_routes
from tools.storage_policy import directory_bytes, file_sha256, stage_growth, temporary_directory, write_hash_reference

STAGE = "etapa1f3"
PUBLIC = ROOT / "urbanflow-web/assets/decision-clearance.json"
GENERATION_END = END
CLEARANCE_END = 2400
WINDOW_FACTOR = CLEARANCE_END // GENERATION_END
LEVELS = (45, 90, 135)
PRIOR_TRIPS = {
    45: (
        ROOT / "results/_tmp/etapa1f1/a/trips.xml",
        ROOT / "results/_tmp/etapa1f1/b/trips.xml",
    ),
    90: (
        ROOT / "results/_tmp/etapa1f2/d90/a/trips.xml",
        ROOT / "results/_tmp/etapa1f2/d90/b/trips.xml",
    ),
    135: (
        ROOT / "results/_tmp/etapa1f2/d135/a/trips.xml",
        ROOT / "results/_tmp/etapa1f2/d135/b/trips.xml",
    ),
}
DIRECTIONS = {
    "s": "de frente",
    "l": "a la izquierda",
    "r": "a la derecha",
    "t": "en U",
    "L": "a la izquierda",
    "R": "a la derecha",
}


def cite(stage, source, name):
    folder = stage / "cited"
    folder.mkdir(parents=True, exist_ok=True)
    write_hash_reference(folder, source, name)


def routes_for(stage, demand):
    """Reutiliza la escala ya publicada. No define otra intensidad."""
    if demand == 45:
        path = SOURCE / "routes.rou.xml"
    else:
        path = ROOT / "results/_tmp/etapa1f2" / f"routes-{demand}.rou.xml"
        expected = scale_routes(SOURCE / "routes.rou.xml", PER_FLOW[demand])
        if not path.is_file() or path.read_bytes() != expected:
            raise DecisionError(
                f"No está el escenario de {demand} vehículos, o no coincide con los 15 flujos de la muestra."
            )
    flows = list(ET.parse(path).iter("flow"))
    if len(flows) != 15 or any(flow.get("end") != str(GENERATION_END) for flow in flows):
        raise DecisionError("La demanda no conserva los 15 flujos con fin en el segundo 240.")
    if any(flow.get("number") != str(PER_FLOW[demand]) for flow in flows):
        raise DecisionError(f"La demanda de {demand} no usa {PER_FLOW[demand]} vehículos por flujo.")
    cite(stage, path, f"routes-{demand}.json")
    return path


def ensure_network(stage):
    cited = ROOT / "results/_tmp/etapa1f1/b-network.net.xml"
    if cited.is_file() and only_maxdur_edit(SOURCE / "network.net.xml", cited):
        cite(stage, cited, "b-network.json")
        return cited
    return prepare_variant_network(stage)


def run_clearance(executable, environment, directory, network, routes):
    """Sigue después del segundo 240. No guarda la traza semafórica."""
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    command = [
        executable, "--net-file", str(network), "--route-files", str(routes),
        "--end", str(CLEARANCE_END), "--step-length", STEP,
        "--seed", str(SEED), "--time-to-teleport", "-1", "--no-step-log", "true",
        "--tripinfo-output", "trips.xml",
        "--tripinfo-output.write-unfinished", "true",
        "--tripinfo-output.write-undeparted", "true",
    ]
    result = subprocess.run(
        command, cwd=directory, env=environment, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    (directory / "sumo.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise DecisionError(f"SUMO terminó con código {result.returncode}. El detalle está en {directory / 'sumo.log'}.")
    if not (directory / "trips.xml").is_file():
        raise DecisionError(f"SUMO no escribió los viajes en {directory}.")
    if (directory / "signal-states.xml").exists():
        raise DecisionError("Esta etapa no guarda la traza semafórica.")


def read_trips(path):
    rows = {}
    rejected = []
    for trip in ET.parse(path).iter("tripinfo"):
        vaporized = trip.get("vaporized") or ""
        if vaporized not in {"", "end"}:
            rejected.append(trip.get("id"))
        rows[trip.get("id")] = {
            "depart": float(trip.get("depart")),
            "arrival": float(trip.get("arrival")),
            "duration": float(trip.get("duration")),
            "waitingTime": float(trip.get("waitingTime")),
        }
    return rows, rejected


def horizon_signature(path):
    rows = {}
    for trip in ET.parse(path).iter("tripinfo"):
        arrival = trip.get("arrival")
        if not arrival or float(arrival) < 0 or float(arrival) > GENERATION_END:
            continue
        rows[trip.get("id")] = (trip.get("duration"), trip.get("waitingTime"), arrival)
    return rows


def partition(rows):
    completed = pending = after = absent = unfinished = 0
    finished = {}
    for key, row in rows.items():
        depart = row["depart"]
        arrival = row["arrival"]
        if depart < 0:
            absent += 1
            continue
        if depart > GENERATION_END:
            after += 1
        if arrival >= 0:
            finished[key] = (row["duration"], row["waitingTime"], depart)
            if arrival <= GENERATION_END:
                completed += 1
            elif depart <= GENERATION_END:
                pending += 1
        else:
            unfinished += 1
            if depart <= GENERATION_END:
                pending += 1
    clearance = None
    if rows and absent == 0 and unfinished == 0:
        clearance = round(max(row["arrival"] for row in rows.values()), 2)
    return {
        "completedAtGeneration": completed,
        "pendingAtGeneration": pending,
        "enteredAfterGeneration": after,
        "notEntered": absent,
        "stillUnfinished": unfinished,
        "clearanceSeconds": clearance,
        "finished": finished,
    }


def level_report(demand, trips_a, trips_b, routes, prior_a, prior_b):
    rows_a, rejected_a = read_trips(trips_a)
    rows_b, rejected_b = read_trips(trips_b)
    if rejected_a or rejected_b:
        raise DecisionError(f"SUMO vaporizó vehículos en la demanda de {demand}.")
    left = partition(rows_a)
    right = partition(rows_b)
    if len(rows_a) != demand or len(rows_b) != demand:
        raise DecisionError(f"La demanda de {demand} no escribió un viaje por vehículo pedido.")
    agrees = (
        horizon_signature(trips_a) == completed_signature(prior_a)
        and horizon_signature(trips_b) == completed_signature(prior_b)
    )
    finished_a = within_generation(left["finished"])
    finished_b = within_generation(right["finished"])
    same = cohort(finished_a, finished_b)
    return {
        "demand": demand,
        "perFlow": PER_FLOW[demand],
        "generationEnd": GENERATION_END,
        "clearanceEnd": CLEARANCE_END,
        "completedAtGeneration": {"a": left["completedAtGeneration"], "b": right["completedAtGeneration"]},
        "pendingAtGeneration": {"a": left["pendingAtGeneration"], "b": right["pendingAtGeneration"]},
        "enteredAfterGeneration": {"a": left["enteredAfterGeneration"], "b": right["enteredAfterGeneration"]},
        "notEntered": {"a": left["notEntered"], "b": right["notEntered"]},
        "clearanceSeconds": {"a": left["clearanceSeconds"], "b": right["clearanceSeconds"]},
        "stillUnfinished": {"a": left["stillUnfinished"], "b": right["stillUnfinished"]},
        "cohort": same,
        "medianTravelChange": median_change(finished_a, finished_b),
        "travelShape": travel_shape(finished_a, finished_b),
        "horizonAgrees": agrees,
        "evidence": {
            "routes": routes.relative_to(ROOT).as_posix(),
            "routesSha256": file_sha256(routes),
            "tripsA": Path(trips_a).relative_to(ROOT).as_posix(),
            "tripsB": Path(trips_b).relative_to(ROOT).as_posix(),
            "logA": Path(trips_a).with_name("sumo.log").relative_to(ROOT).as_posix(),
            "logB": Path(trips_b).with_name("sumo.log").relative_to(ROOT).as_posix(),
        },
    }


def travel_shape(finished_a, finished_b):
    shared = sorted(set(finished_a) & set(finished_b))
    deltas = [finished_b[key][0] - finished_a[key][0] for key in shared]
    return {
        "unchanged": sum(1 for item in deltas if abs(item) <= 0.05),
        "atLeast60sSlowerInA": sum(1 for item in deltas if item <= -60),
    }


def median_change(finished_a, finished_b):
    shared = sorted(set(finished_a) & set(finished_b))
    if not shared:
        return None
    return round(median(finished_b[key][0] - finished_a[key][0] for key in shared), 2)


def within_generation(finished):
    return {
        key: value for key, value in finished.items()
        if 0 <= value[2] <= GENERATION_END
    }


def warned_indexes(log_text, controller):
    marker = "linkIndex "
    found = []
    for line in log_text.splitlines():
        if controller not in line or "has no controlling detector" not in line:
            continue
        start = line.find(marker)
        if start < 0:
            continue
        numbers = line[start + len(marker):].split(" has no controlling detector", 1)[0]
        found.append(tuple(int(item) for item in numbers.split(",") if item.strip()))
    if len(found) != 1:
        raise DecisionError("El aviso de detectores no aparece una sola vez en el registro de SUMO.")
    return found[0]


def link_movements(network, controller):
    root = ET.parse(network).getroot()
    edges = {edge.get("id"): edge for edge in root.iter("edge")}
    lanes = {lane.get("id"): lane for lane in root.iter("lane")}
    state = None
    for logic in root.iter("tlLogic"):
        if logic.get("id") != controller:
            continue
        for phase in logic.findall("phase"):
            if phase.get("state") == PHASE_STATE:
                state = phase.get("state")
                break
    if state is None:
        raise DecisionError("La red no tiene la fase autorizada de Roosevelt y Honduras.")
    movements = []
    for connection in root.iter("connection"):
        if connection.get("tl") != controller:
            continue
        index = int(connection.get("linkIndex"))
        origin = connection.get("from")
        destination = connection.get("to")
        lane = lanes[f"{origin}_{connection.get('fromLane')}"]
        movements.append({
            "linkIndex": index,
            "from": origin,
            "fromName": edges[origin].get("name") or origin,
            "to": destination,
            "toName": edges[destination].get("name") or destination,
            "direction": DIRECTIONS.get(connection.get("dir"), connection.get("dir")),
            "fromLane": int(connection.get("fromLane")),
            "laneLength": round(float(lane.get("length")), 2),
            "greenInCappedPhase": state[index] in "Gg",
        })
    movements.sort(key=lambda item: item["linkIndex"])
    return movements


def detector_report(network, logs):
    indexes = [warned_indexes(path.read_text(encoding="utf-8"), CONTROLLER) for path in logs]
    if any(item != indexes[0] for item in indexes):
        raise DecisionError("El aviso de detectores no es el mismo en A y en B.")
    warned = indexes[0]
    movements = link_movements(network, CONTROLLER)
    known = {item["linkIndex"] for item in movements}
    if any(index not in known for index in warned):
        raise DecisionError("El aviso nombra un linkIndex que no está en el controlador.")
    blinded = [item for item in movements if item["linkIndex"] in warned]
    detected = sorted({
        item["fromName"] for item in movements
        if item["greenInCappedPhase"] and item["linkIndex"] not in warned
    })
    return {
        "controller": CONTROLLER,
        "warning": "has no controlling detector",
        "linkIndexes": list(warned),
        "identicalBetweenVariants": True,
        "movements": blinded,
        "cappedPhaseWithoutDetector": [item["linkIndex"] for item in blinded if item["greenInCappedPhase"]],
        "cappedPhaseDetectedApproaches": detected,
        "conditionsInterpretation": True,
        "interpretation": interpret(blinded, detected),
    }


def spanish_length(value):
    return f"{value:.2f}".replace(".", ",")


def short_phrase(item):
    return (
        f"{item['linkIndex']} ({item['fromName']}, carril {item['fromLane']}, "
        f"{item['direction']} hacia {item['toName']})"
    )


def interpret(blinded, detected):
    capped = [item for item in blinded if item["greenInCappedPhase"]]
    other = [item for item in blinded if not item["greenInCappedPhase"]]
    ordered = [spanish_length(item) + " m" for item in sorted({item["laneLength"] for item in blinded})]
    lengths = ordered[0] if len(ordered) == 1 else ", ".join(ordered[:-1]) + " y " + ordered[-1]
    approaches = ", ".join(detected) if detected else "ningún acceso"
    return (
        f"SUMO avisa has no controlling detector en {CONTROLLER} para los linkIndex "
        f"{', '.join(str(item['linkIndex']) for item in blinded)}. "
        f"Son movimientos internos del cruce unido. Los tramos miden {lengths}. "
        f"En la fase cuyo máximo pasa de 50 s a 15 s quedan sin detector {', '.join(short_phrase(item) for item in capped)}. "
        f"En la otra fase verde quedan sin detector {', '.join(short_phrase(item) for item in other)}. "
        "SUMO no usa esos enlaces para alargar la verde. "
        f"Los accesos con detector en la fase modificada son {approaches}. "
        "A y B comparten el aviso. Los detectores y el programa quedan como están en la red guardada. "
        "La comparación aísla el máximo de esa fase con el programa inferido y la demanda sintética."
    )


def spanish_seconds(value):
    return f"{value:.2f}".replace(".", ",")


def conclude(levels):
    factor_word = {5: "cinco", 10: "diez"}[WINDOW_FACTOR]
    pending = "; ".join(
        f"{level['demand']}: {level['pendingAtGeneration']['a']} y {level['pendingAtGeneration']['b']}"
        for level in levels
    )
    cleared = []
    blocked = []
    for level in levels:
        left = level["clearanceSeconds"]["a"]
        right = level["clearanceSeconds"]["b"]
        if left is None or right is None:
            blocked.append(
                f"con {level['demand']} quedan {level['stillUnfinished']['a']} en A y {level['stillUnfinished']['b']} en B"
            )
        else:
            cleared.append(
                f"{level['demand']} a los {spanish_seconds(left)} s en A y {spanish_seconds(right)} s en B"
            )
    if cleared and not blocked:
        clearance = "La demanda termina de despejarse en " + "; ".join(cleared) + "."
    elif blocked and not cleared:
        clearance = f"Al segundo {CLEARANCE_END} la demanda sigue en la red: " + "; ".join(blocked) + "."
    else:
        clearance = (
            "Se despeja " + "; ".join(cleared) + ". "
            f"Al segundo {CLEARANCE_END}, " + "; ".join(blocked) + "."
        )
    late = [str(level["demand"]) for level in levels if level["enteredAfterGeneration"]["a"] or level["enteredAfterGeneration"]["b"]]
    if late:
        late_sentence = f"En {', '.join(late)} hay salidas después del segundo 240. Esos viajes quedan fuera de la cohorte."
    else:
        late_sentence = "Ningún vehículo sale después del segundo 240."
    changes = ", ".join(
        spanish_seconds(level["cohort"]["meanTravel"]["absolute"]) + " s"
        for level in levels if level["cohort"]["meanTravel"]
    )
    waits = ", ".join(
        spanish_seconds(level["cohort"]["meanWait"]["absolute"]) + " s"
        for level in levels if level["cohort"]["meanWait"]
    )
    later = []
    for level in levels:
        left = level["clearanceSeconds"]["a"]
        right = level["clearanceSeconds"]["b"]
        if left is None or right is None:
            continue
        later.append(spanish_seconds(left - right) + " s")
    if len(later) == len(levels):
        gap_sentence = "A se vacía más tarde: " + ", ".join(
            f"{spanish_seconds(level['clearanceSeconds']['a'] - level['clearanceSeconds']['b'])} s con {level['demand']}"
            for level in levels
        ) + "."
    else:
        gap_sentence = "El despeje solo se informa en los niveles que se vacían."
    shapes = []
    for level in levels:
        shape = level["travelShape"]
        text = f"en {level['demand']}, {shape['unchanged']} de {level['cohort']['count']} no cambian"
        if shape["atLeast60sSlowerInA"]:
            text += f" y {shape['atLeast60sSlowerInA']} duran al menos 60 s más en A"
        shapes.append(text)
    medians = ", ".join(spanish_seconds(level["medianTravelChange"]) + " s" for level in levels)
    long_demands = [str(level["demand"]) for level in levels if level["travelShape"]["atLeast60sSlowerInA"]]
    if len(long_demands) == 1:
        long_text = long_demands[0]
    elif long_demands:
        long_text = ", ".join(long_demands[:-1]) + " y " + long_demands[-1]
    else:
        long_text = ""
    drag = (
        f"En {long_text} el promedio lo arrastran esos viajes largos, y el despeje es la última de esas llegadas. "
        if long_text else ""
    )
    skew_sentence = (
        f"La mediana del cambio de viaje es {medians}. "
        + ". ".join(sentence[0].upper() + sentence[1:] for sentence in shapes) + ". "
        + drag
        + f"El cambio medio de espera es {waits}."
    )
    unfinished = [level for level in levels if level["stillUnfinished"]["a"] or level["stillUnfinished"]["b"]]
    if unfinished:
        censored = (
            "En los niveles que no se despejan, ese promedio deja afuera a quienes siguen en la red "
            "y no mide toda la demanda."
        )
    else:
        censored = "En los tres niveles la cohorte incluye a todos los vehículos que salieron."
    return " ".join([
        "Las salidas quedan definidas entre el begin de cada flujo y el segundo 240. "
        f"La simulación sigue hasta el segundo {CLEARANCE_END}, {factor_word} veces esa ventana, y no agrega flujos. "
        "45, 90 y 135 vehículos son la muestra y sus múltiplos enteros sobre los mismos 15 recorridos. "
        "La demanda es sintética. El programa es el que SUMO infirió, no un plan de la Intendencia.",
        f"Al segundo 240 siguen pendientes {pending}.",
        clearance,
        late_sentence,
        "La cohorte junta los viajes que salen dentro de la ventana y llegan en las dos variantes. "
        f"El cambio medio de viaje es {changes}.",
        gap_sentence,
        skew_sentence,
        censored,
        "El aviso de detectores es el mismo en las seis corridas.",
    ])


def build_report(levels, detector, version, network):
    return {
        "experimental": True,
        "calibrated": False,
        "seasonal": False,
        "title": "Despeje de la demanda",
        "note": (
            f"La demanda se genera hasta el segundo {GENERATION_END} y la simulación sigue hasta el segundo {CLEARANCE_END}. "
            "A y B comparten rutas, horarios, semilla 42 y red. "
            "Solo cambia el máximo de la primera fase, de 50 s a 15 s."
        ),
        "criterion": (
            "Completaron al 240 son los que llegan hasta ese segundo. "
            "Pendientes al 240 son los que ya salieron y todavía no llegan. "
            "El despeje es el instante de la última llegada cuando no queda nadie, ni sin salir ni sin llegar. "
            "La cohorte de tiempos excluye a quien no llega en las dos variantes y a quien sale después del 240. "
            f"El límite de {CLEARANCE_END} s es {WINDOW_FACTOR} veces la ventana de generación. "
            "Los programas son los que SUMO infirió y la demanda es sintética, sin calibración municipal."
        ),
        "levels": levels,
        "detector": detector,
        "conclusion": conclude(levels),
        "network": network.relative_to(ROOT).as_posix(),
        "sumo": version,
    }


def publish(report, stage):
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(text, encoding="utf-8")
    (stage / "clearance.json").write_text(text, encoding="utf-8")


def prepare_stage(stage):
    for child in list(stage.iterdir()):
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main():
    before = source_hashes()
    results_before = directory_bytes(ROOT / "results")
    executable, environment = locate_sumo()
    version = sumo_version(executable, environment)
    stage = temporary_directory(ROOT, STAGE)
    prepare_stage(stage)
    network = ensure_network(stage)
    cite(stage, SOURCE / "network.net.xml", "a-network.json")
    levels = []
    logs = []
    for demand in LEVELS:
        prior_a, prior_b = PRIOR_TRIPS[demand]
        if not prior_a.is_file() or not prior_b.is_file():
            raise DecisionError(f"Falta la corrida de {demand} vehículos con la que se compara el primer tramo de 240 s.")
        routes = routes_for(stage, demand)
        folder = stage / f"d{demand}"
        run_clearance(executable, environment, folder / "a", SOURCE / "network.net.xml", routes)
        run_clearance(executable, environment, folder / "b", network, routes)
        cite(stage, prior_a, f"horizon-d{demand}-a.json")
        cite(stage, prior_b, f"horizon-d{demand}-b.json")
        report = level_report(demand, folder / "a" / "trips.xml", folder / "b" / "trips.xml", routes, prior_a, prior_b)
        if not report["horizonAgrees"]:
            raise DecisionError(f"Con {demand} vehículos los viajes terminados hasta el segundo 240 no coinciden con la corrida anterior.")
        if demand == 45 and horizon_signature(folder / "a" / "trips.xml") != completed_signature(SOURCE / "trips.xml"):
            raise DecisionError("Los viajes de 45 vehículos terminados hasta el segundo 240 no reproducen la corrida guardada.")
        levels.append(report)
        logs.extend((folder / "a" / "sumo.log", folder / "b" / "sumo.log"))
    if source_hashes() != before:
        PUBLIC.unlink(missing_ok=True)
        raise DecisionError("La corrida guardada cambió durante el experimento.")
    detector = detector_report(SOURCE / "network.net.xml", logs)
    report = build_report(levels, detector, version, network)
    publish(report, stage)
    growth = stage_growth(results_before, directory_bytes(ROOT / "results"))
    print(json.dumps({
        "levels": [{
            "demand": level["demand"],
            "completedAtGeneration": level["completedAtGeneration"],
            "pendingAtGeneration": level["pendingAtGeneration"],
            "clearanceSeconds": level["clearanceSeconds"],
            "stillUnfinished": level["stillUnfinished"],
            "enteredAfterGeneration": level["enteredAfterGeneration"],
            "cohort": level["cohort"]["count"],
            "travel": None if not level["cohort"]["meanTravel"] else level["cohort"]["meanTravel"]["absolute"],
            "medianTravelChange": level["medianTravelChange"],
            "wait": None if not level["cohort"]["meanWait"] else level["cohort"]["meanWait"]["absolute"],
        } for level in levels],
        "detector": detector["linkIndexes"],
        "cappedWithoutDetector": detector["cappedPhaseWithoutDetector"],
        "bytes": growth,
        "stageBytes": directory_bytes(stage),
        "conclusion": report["conclusion"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except DecisionError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
