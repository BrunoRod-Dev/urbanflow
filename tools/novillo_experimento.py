"""Candidata experimental de Novillo Alegre, independiente de la red 1G.1.

Incluye las vías 252069937 y 101195613 en ambos sentidos porque OSM no les
pone oneway. No modifica redes certificadas ni crea el enlace Francia–Artigas.
La comparación A/B solo seguiría si los dos recorridos fueran legales y
terminaran en el mismo borde de SUMO.
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tools.novillo_alegre as geometry
import tools.storage_policy as storage
STAGE = "etapa1g3"
DIRECTORY = storage.temporary_directory(ROOT, STAGE)
PUBLIC = ROOT / "urbanflow-web" / "assets" / "novillo-experimento.json"
SOURCE_HASH = "868b473a814999649af1d03ba164be232320c9dd82a229d5514315c0afc3a272"
CERTIFIED_NET = ROOT / "results" / "_tmp" / "etapa1g1" / "red.net.xml"
CERTIFIED_NET_SHA256 = "3636e0efc5f2856fe38ca011e9f103746f27c975620424ad11b1e8e59bafa108"
REPLAY = ROOT / "results/etapa1c5-sector01/candidata/01c5b202611140000000000000000001/replay.json"
REPLAY_SHA256 = "03b534e910cd373360eb595fa463dff5e7ee9f743368b67378c7e6aca141080b"
EXPERIMENTAL_SPEED_MS = "8.33"
EXPERIMENTAL_SPEED_KMH = 30
IMPLICIT_BOTH = ("252069937", "101195613")
RING = geometry.RING
ORIGIN = geometry.ORIGIN
DESTINATION = geometry.DESTINATION
FRANCIA_END = geometry.FRANCIA_END
ARTIGAS_FRANCIA = "1155354703"
NETCONVERT_FLAGS = (
    "--output.street-names", "true",
    "--geometry.remove", "false",
    "--edges.join", "false",
    "--tls.guess-signals", "false",
    "--tls.default-type", "static",
    "--tls.join", "false",
    "--ramps.guess", "false",
    "--sidewalks.guess", "false",
    "--osm.sidewalks", "false",
    "--osm.turn-lanes", "false",
    "--no-turnarounds", "true",
    "--no-turnarounds.tls", "true",
    "--keep-edges.by-vclass", "passenger",
    "--remove-edges.isolated", "false",
)


def edge_way(edge_id):
    return edge_id.split("#", 1)[0].lstrip("-")


def candidate_items(ways, points):
    """Red verificada de 1G.1 más las dos vías de Pedragosa, con sus etiquetas OSM."""
    rings = [geometry.ring_report(way_id, ways, points) for way_id in geometry.RINGS]
    items = geometry.mark_verified(geometry.clip_items(ways), rings)
    chosen = [item for item in items if item["verified"] or item["id"] in IMPLICIT_BOTH]
    present = {item["id"] for item in chosen}
    missing = [way_id for way_id in IMPLICIT_BOTH if way_id not in present]
    if missing:
        raise RuntimeError(f"La candidata no contiene {', '.join(missing)}.")
    for item in chosen:
        if item["id"] not in IMPLICIT_BOTH:
            continue
        if item["verified"] or item["data"].get("oneway") is not None:
            raise RuntimeError(f"{item['id']} ya no es una vía sin oneway excluida por 1G.1.")
    return chosen


def compile_candidate(directory):
    executable, environment = geometry.locate_netconvert()
    command = [executable, "--osm-files", "red-candidata.osm.xml", "--output-file", "red.net.xml", *NETCONVERT_FLAGS]
    result = subprocess.run(command, cwd=directory, env=environment, capture_output=True, text=True, timeout=90)
    log = directory / "netconvert.log"
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("netconvert falló. El detalle quedó en netconvert.log.")
    return log


def load_graph(path):
    root = ET.parse(path).getroot()
    edges = {}
    for edge in root.findall("edge"):
        if edge.get("function") == "internal":
            continue
        edges[edge.get("id")] = edge
    successors = defaultdict(set)
    for connection in root.findall("connection"):
        source = connection.get("from")
        target = connection.get("to")
        if source in edges and target in edges:
            successors[source].add(target)
    return edges, successors


def reachable(successors, start, banned):
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for target in successors[current]:
            if target in seen or target in banned:
                continue
            seen.add(target)
            queue.append(target)
    return seen


def shortest(successors, start, goals, banned):
    seen = {start}
    queue = deque([(start, [start])])
    while queue:
        current, path = queue.popleft()
        if current in goals and current != start:
            return path
        for target in successors[current]:
            if target in seen or target in banned:
                continue
            seen.add(target)
            queue.append((target, path + [target]))
    return None


def ways_of(path):
    result = []
    for edge_id in path:
        way_id = edge_way(edge_id)
        if not result or result[-1] != way_id:
            result.append(way_id)
    return result


def speeds_of(path, way_id):
    speeds = []
    for edge in ET.parse(path).getroot().findall("edge"):
        if edge.get("function") == "internal" or edge_way(edge.get("id")) != way_id:
            continue
        speeds.extend(lane.get("speed") for lane in edge.findall("lane"))
    return speeds


def apply_experimental_speed(path):
    """Tope de prueba en todos los carriles. No es la señalización publicada."""
    tree = ET.parse(path)
    lanes = 0
    for lane in tree.getroot().iter("lane"):
        lane.set("speed", EXPERIMENTAL_SPEED_MS)
        lanes += 1
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return lanes


def restriction_at_destination(path):
    found = []
    for relation in ET.parse(path).findall("relation"):
        tags = {tag.get("k"): tag.get("v") for tag in relation.findall("tag")}
        if tags.get("type") != "restriction":
            continue
        roles = {member.get("role"): member.get("ref") for member in relation.findall("member")}
        if roles.get("from") == "983236122" and roles.get("to") == "311824953" and roles.get("via") == DESTINATION:
            found.append({
                "id": relation.get("id"),
                "type": tags.get("restriction"),
                "from": "983236122",
                "to": "311824953",
                "via": DESTINATION,
            })
    return found


def arrivals(net_path, edge_ids):
    root = ET.parse(net_path).getroot()
    by_id = {edge.get("id"): edge for edge in root.findall("edge")}
    result = []
    for edge_id in edge_ids:
        edge = by_id[edge_id]
        continuations = []
        for connection in root.findall("connection"):
            target = connection.get("to")
            if connection.get("from") != edge_id or target is None or target.startswith(":"):
                continue
            continuations.append({
                "to": target,
                "dir": connection.get("dir"),
                "state": connection.get("state"),
            })
        result.append({
            "edge": edge_id,
            "from": edge.get("from"),
            "to": edge.get("to"),
            "lengths": [lane.get("length") for lane in edge.findall("lane")],
            "continuations": continuations,
        })
    return result


def assess(net_path):
    edges, successors = load_graph(net_path)
    starts = [
        edge_id for edge_id, edge in edges.items()
        if edge.get("from") == ORIGIN and edge_way(edge_id) == "983235082"
    ]
    if len(starts) != 1:
        raise RuntimeError(f"El origen SUMO no es único: {starts}.")
    start = starts[0]
    pedragosa = {edge_id for edge_id in edges if edge_way(edge_id) in IMPLICIT_BOTH}
    del_mar = {edge_id for edge_id in edges if edge_way(edge_id) == "454567064"}
    ring_edges = {edge_id for edge_id in edges if edge_way(edge_id) == RING}
    through_seen = reachable(successors, start, pedragosa | del_mar)
    avoid_seen = reachable(successors, start, ring_edges)
    through_goals = {edge_id for edge_id in through_seen if edges[edge_id].get("to") == DESTINATION}
    avoid_goals = {edge_id for edge_id in avoid_seen if edges[edge_id].get("to") == DESTINATION}
    through_path = shortest(successors, start, through_goals, pedragosa | del_mar)
    avoid_path = shortest(successors, start, avoid_goals, ring_edges)
    through_ways = ways_of(through_path or [])
    avoid_ways = ways_of(avoid_path or [])
    through_next = {target for edge_id in through_goals for target in successors[edge_id]}
    avoid_next = {target for edge_id in avoid_goals for target in successors[edge_id]}
    both_present = all(
        any(edge_way(edge_id) == way_id and not edge_id.startswith("-") for edge_id in edges)
        and any(edge_way(edge_id) == way_id and edge_id.startswith("-") for edge_id in edges)
        for way_id in IMPLICIT_BOTH
    )
    francia = [
        edge_id for edge_id, edge in edges.items()
        if {edge.get("from"), edge.get("to")} == {FRANCIA_END, ARTIGAS_FRANCIA}
    ]
    return {
        "originEdge": start,
        "originNode": ORIGIN,
        "destinationNode": DESTINATION,
        "throughLegal": bool(through_path) and RING in through_ways and "454567064" not in through_ways,
        "avoidLegal": (
            bool(avoid_path)
            and set(IMPLICIT_BOTH).issubset(avoid_ways)
            and "454567064" in avoid_ways
            and RING not in avoid_ways
        ),
        "throughWays": through_ways,
        "avoidWays": avoid_ways,
        "throughEdges": through_path or [],
        "avoidEdges": avoid_path or [],
        "throughArrivalEdges": sorted(through_goals),
        "avoidArrivalEdges": sorted(avoid_goals),
        "sharedDestinationEdges": sorted(through_goals & avoid_goals),
        "sharedContinuationEdges": sorted(through_next & avoid_next),
        "sameOriginEdge": True,
        "samePhysicalNode": bool(through_goals) and bool(avoid_goals),
        "bidirectionalPedragosa": both_present,
        "franciaConnection": francia,
    }


def unchanged(path, expected):
    return path.is_file() and storage.file_sha256(path) == expected


def build():
    if not unchanged(CERTIFIED_NET, CERTIFIED_NET_SHA256) or not unchanged(REPLAY, REPLAY_SHA256):
        raise RuntimeError("La red 1G.1 o el replay certificado ya no coinciden. No se compiló otra candidata.")
    snapshot = ROOT / geometry.SNAPSHOT
    if storage.file_sha256(snapshot) != SOURCE_HASH:
        raise RuntimeError("El snapshot OSM cambió. No se compiló otra candidata.")
    storage.cleanup_temporary(ROOT, STAGE)
    DIRECTORY.mkdir(parents=True)
    _attributes, nodes, points, ways, relations = geometry.regional_network()
    items = candidate_items(ways, points)
    geometry.write_osm(DIRECTORY / "red-candidata.osm.xml", nodes, items, relations)
    log = compile_candidate(DIRECTORY)
    net_path = DIRECTORY / "red.net.xml"
    ring_before = speeds_of(net_path, RING)
    lanes = apply_experimental_speed(net_path)
    storage.write_hash_reference(DIRECTORY, snapshot, "snapshot.ref.json")
    checked = assess(net_path)
    if checked["franciaConnection"]:
        raise RuntimeError("Apareció una conexión Francia–Artigas que esta etapa no autoriza.")
    if not checked["bidirectionalPedragosa"]:
        raise RuntimeError("Pedragosa no quedó en ambos sentidos dentro de la red compilada.")
    restrictions = restriction_at_destination(DIRECTORY / "red-candidata.osm.xml")
    comparable = (
        checked["throughLegal"]
        and checked["avoidLegal"]
        and (checked["sharedDestinationEdges"] or checked["sharedContinuationEdges"])
    )
    if comparable:
        raise RuntimeError("Hay un destino SUMO común. La corrida no está hecha y no se publican resultados.")
    if not restrictions:
        raise RuntimeError("La restricción del cruce no está en la candidata. No se documenta un bloqueo inventado.")
    report = {
        "stage": "1G.3",
        "case": "Novillo Alegre",
        "scope": "Prueba geométrica y operativa con demanda sintética. No es una simulación calibrada del verano.",
        "experimental": True,
        "calibrated": False,
        "seasonal": False,
        "simulated": None,
        "comparison": None,
        "summary": (
            "Los dos recorridos son legales, salen del mismo borde y llegan al mismo cruce. "
            "No comparten un borde de destino de SUMO, así que la comparación A/B no se ejecutó."
        ),
        "speedAssumption": {
            "kmh": EXPERIMENTAL_SPEED_KMH,
            "ms": float(EXPERIMENTAL_SPEED_MS),
            "lanes": lanes,
            "ringMetersPerSecondBefore": sorted(set(ring_before)),
            "appliedToCandidate": True,
            "usedInSimulation": False,
            "signage": False,
            "note": (
                "30 km/h es un supuesto para las dos variantes, aplicado a la candidata "
                "para que el predeterminado de 100 km/h del anillo no quede disponible. "
                "No es señalización real y ninguna variante llegó a simularse."
            ),
        },
        "routes": checked,
        "arrivals": arrivals(net_path, checked["throughArrivalEdges"] + checked["avoidArrivalEdges"]),
        "restriction": restrictions,
        "blockage": {
            "comparison": True,
            "reason": (
                f"El recorrido de la rotonda termina en {', '.join(checked['throughArrivalEdges'])} "
                f"y el desvío en {', '.join(checked['avoidArrivalEdges'])}. "
                f"Los dos entran al cruce {DESTINATION}. La salida 311824953 está permitida desde Avenida del Mar "
                f"y prohibida desde Artigas por la restricción OSM {restrictions[0]['id']} "
                f"({restrictions[0]['type']}). No hay otro borde que ambos puedan usar como destino. "
                "No se creó esa conexión ni se inventó un destino común."
            ),
        },
        "limits": [
            "La demanda, el porcentaje desviado y el horizonte no se ejecutaron: sin destino común no hay comparación.",
            "30 km/h queda en la candidata como supuesto. No representa la señal del anillo.",
            "El enlace faltante entre Francia y Artigas no se construyó.",
            "La red certificada de 1G.1 sigue sin las dos vías de Pedragosa.",
        ],
        "netconvertLog": str(log.relative_to(ROOT)).replace("\\", "/"),
        "candidate": str(DIRECTORY.relative_to(ROOT)).replace("\\", "/"),
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (DIRECTORY / "caso.json").write_text(payload, encoding="utf-8")
    PUBLIC.write_text(payload, encoding="utf-8")
    if not unchanged(CERTIFIED_NET, CERTIFIED_NET_SHA256) or not unchanged(REPLAY, REPLAY_SHA256):
        raise RuntimeError("La compilación alteró una red protegida.")
    return report


def main():
    report = build()
    print(json.dumps({
        "comparison": report["comparison"],
        "through": report["routes"]["throughLegal"],
        "avoid": report["routes"]["avoidLegal"],
        "shared": report["routes"]["sharedDestinationEdges"],
        "continuation": report["routes"]["sharedContinuationEdges"],
        "bytes": storage.directory_bytes(DIRECTORY),
        "publicBytes": PUBLIC.stat().st_size,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
