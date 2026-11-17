"""Caso geométrico de la rotonda Roosevelt–Artigas, vía OSM 100089298.

Compila solo el recorte aprobado. El sentido de un anillo se acepta si está
cerrado, gira en sentido antihorario y los accesos con oneway explícito entran
o salen de acuerdo con ese dibujo. Una vía sin oneway no entra a la red
transitable. Si el desvío por Pedragosa y Avenida del Mar depende de una vía
así, la comparación no se simula.
"""

from collections import defaultdict, deque
import json
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sumo_scenario.regional_inventory import meters, tags
from sumo_scenario.regional_map import regional_network
from tools.storage_policy import (
    NETCONVERT_SHA256,
    SNAPSHOT,
    cleanup_temporary,
    directory_bytes,
    file_sha256,
    temporary_directory,
    write_hash_reference,
)


STAGE = "etapa1g1"
RING = "100089298"
PARADA5 = "70521182"
ROOSEVELT_RING = "100473811"
ORIGIN = "1155355178"
DESTINATION = "3175611488"
ARTIGAS_NORTH = "6871194567"
SIGNAL = "1918169796"
DEL_MAR_NODE = "1167219966"
FRANCIA_END = "1156825106"
PUBLIC = ROOT / "urbanflow-web/assets/novillo-alegre.json"
GEOJSON = ROOT / "urbanflow-web/assets/novillo-alegre.geojson"
VEHICLE = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "service", "living_street", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
RESTRICTED = {"no", "private", "destination", "customers", "delivery"}
RINGS = (RING, PARADA5, ROOSEVELT_RING)
EXCLUDED = (
    "185329451", "100473863", "100070328", "100473830", "311824955",
    "101195541", "1419127818", "252069933", "185203624", "185219449",
)
TRIMS = {
    "449294015": ("1155355261", "1155354947"),
    "101105024": (DEL_MAR_NODE, "1918169545"),
    "101195613": ("1162020617", DEL_MAR_NODE),
}
WAYS = {
    RING: "anillo",
    PARADA5: "parada5",
    ROOSEVELT_RING: "roosevelt",
    "983235082": "artigas",
    "983235081": "artigas",
    "100089295": "artigas",
    "100089299": "artigas",
    "29235087": "artigas",
    "311824968": "artigas",
    "449294015": "artigas",
    "983236122": "artigas",
    "311824954": "artigas",
    "311824960": "artigas",
    "311824964": "artigas",
    "482520532": "roosevelt",
    "482520534": "roosevelt",
    "228982144": "roosevelt",
    "230376885": "roosevelt",
    "230376902": "roosevelt",
    "230376874": "roosevelt",
    "100473846": "roosevelt",
    "100522079": "pedragosa",
    "252069936": "pedragosa",
    "100522082": "pedragosa",
    "185203622": "pedragosa",
    "185203623": "pedragosa",
    "100522073": "pedragosa",
    "252069935": "pedragosa",
    "100522100": "pedragosa",
    "100522077": "pedragosa",
    "100522083": "pedragosa",
    "100522092": "pedragosa",
    "100522122": "pedragosa",
    "100522118": "pedragosa",
    "101195648": "pedragosa",
    "252069937": "pedragosa",
    "101195613": "pedragosa",
    "101105024": "delmar",
    "311824952": "delmar",
    "454567064": "delmar",
    "983236123": "delmar",
    "311824953": "delmar",
    "311824950": "cordoba",
    "100522069": "francia",
    "983235083": "francia",
    "100070316": "francia",
    "101105003": "paso",
    "101105029": "paso",
}
LABELS = {
    "anillo": ("Rotonda", "#9f1239"),
    "parada5": ("Parada 5", "#8a4b08"),
    "roosevelt": ("Roosevelt", "#1d4e89"),
    "artigas": ("Artigas", "#0f6e56"),
    "pedragosa": ("Pedragosa", "#9a3412"),
    "delmar": ("Avenida del Mar", "#0e7490"),
    "francia": ("Francia", "#6b3fa0"),
    "paso": ("Paso de la Cadena", "#64748b"),
    "cordoba": ("Boca de Córdoba", "#64748b"),
}
ANCHORS = (
    ("100089295", -1, RING),
    ("29235087", 0, RING),
    ("311824968", -1, RING),
    ("228982144", -1, RING),
    ("230376874", -1, RING),
    ("482520532", -1, None),
    ("983235081", -1, PARADA5),
    ("100089295", 0, PARADA5),
    ("449294015", 0, PARADA5),
    ("230376902", -1, ROOSEVELT_RING),
    ("100473846", 0, ROOSEVELT_RING),
    ("100522118", 0, ROOSEVELT_RING),
    ("983235082", 0, None),
    ("29235087", -1, None),
    ("983236122", -1, None),
    ("454567064", -1, None),
)


class NovilloError(RuntimeError):
    """El recorte aprobado no se puede publicar con esta comprobación."""


def explicit_sense(data):
    value = data.get("oneway")
    if value in ("yes", "1", "true"):
        return "forward"
    if value == "-1":
        return "reverse"
    if value in ("no", "0", "false"):
        return "both"
    return None


def restricted(data):
    access = next((data[key] for key in ("motorcar", "motor_vehicle", "vehicle", "access") if key in data), None)
    return access in RESTRICTED


def shoelace(refs, points):
    area = 0.0
    for start, end in zip(refs, refs[1:]):
        ax, ay = points[start]
        bx, by = points[end]
        area += ax * by - bx * ay
    return area


def slice_refs(refs, start, end, way_id):
    try:
        first, last = refs.index(start), refs.index(end)
    except ValueError as error:
        raise NovilloError(f"La vía {way_id} no contiene el corte {start}–{end}.") from error
    if first > last:
        raise NovilloError(f"El corte de la vía {way_id} invierte el orden de los nodos.")
    return refs[first:last + 1]


def ring_report(way_id, ways, points):
    element, refs = ways[way_id]
    data = tags(element)
    closed = len(refs) >= 4 and refs[0] == refs[-1]
    area = shoelace(refs, points)
    ring_nodes = set(refs)
    entries, exits, unverified, contradictions, review = [], [], [], [], []
    for other_id, (other, other_refs) in ways.items():
        if other_id == way_id or not other_refs:
            continue
        info = tags(other)
        if info.get("highway") not in VEHICLE:
            continue
        if not (set(other_refs) & ring_nodes):
            continue
        sense = explicit_sense(info)
        start_on = other_refs[0] in ring_nodes
        end_on = other_refs[-1] in ring_nodes
        if sense is None or restricted(info):
            unverified.append(other_id)
            continue
        travel_start, travel_end = (other_refs[-1], other_refs[0]) if sense == "reverse" else (other_refs[0], other_refs[-1])
        leaves = travel_start in ring_nodes and travel_end not in ring_nodes
        arrives = travel_end in ring_nodes and travel_start not in ring_nodes
        if sense == "both" and (start_on or end_on):
            review.append(other_id)
        elif arrives:
            entries.append(other_id)
        elif leaves:
            exits.append(other_id)
        elif start_on and end_on:
            review.append(other_id)
        elif start_on or end_on:
            contradictions.append(other_id)
        else:
            review.append(other_id)
    accepted = closed and area > 0 and not contradictions
    return {
        "id": way_id,
        "closed": closed,
        "counterclockwise": area > 0,
        "area": area,
        "accepted": accepted,
        "entries": sorted(entries, key=int),
        "exits": sorted(exits, key=int),
        "unverifiedApproaches": sorted(unverified, key=int),
        "contradictions": sorted(contradictions, key=int),
        "review": sorted(review, key=int),
        "oneway": data.get("oneway"),
        "lanes": data.get("lanes"),
        "maxspeed": data.get("maxspeed"),
        "name": data.get("name"),
    }


def clip_items(ways):
    items = []
    for way_id, street in WAYS.items():
        element, refs = ways[way_id]
        if way_id in TRIMS:
            refs = slice_refs(refs, *TRIMS[way_id], way_id)
        label, color = LABELS[street]
        items.append({
            "id": way_id,
            "element": element,
            "refs": refs,
            "data": tags(element),
            "street": street,
            "label": label,
            "color": color,
        })
    return items


def check_anchors(ways):
    for way_id, index, ring_id in ANCHORS:
        node = ways[way_id][1][index]
        if way_id == "983235082" and node != ORIGIN:
            raise NovilloError("El origen dejó de ser el nodo de Artigas en Francia.")
        if way_id == "29235087" and index == -1 and node != ARTIGAS_NORTH:
            raise NovilloError("Artigas norte ya no termina en el nodo del cruce con Avenida del Mar.")
        if way_id in {"983236122", "454567064"} and node != DESTINATION:
            raise NovilloError("El empalme de Artigas y Avenida del Mar cambió de nodo.")
        if way_id == "482520532" and node != SIGNAL:
            raise NovilloError("Roosevelt ya no termina en el semáforo 1918169796.")
        if ring_id and node not in set(ways[ring_id][1]):
            raise NovilloError(f"La vía {way_id} ya no toca el anillo {ring_id} en el nodo esperado.")


def mark_verified(items, rings):
    accepted = {item["id"] for item in rings if item["accepted"]}
    for item in items:
        sense = explicit_sense(item["data"])
        if item["id"] in RINGS:
            item["sense"] = "forward" if item["id"] in accepted else None
        elif restricted(item["data"]):
            item["sense"] = None
        else:
            item["sense"] = sense
        item["verified"] = item["sense"] is not None
    return items


def add_edges(graph, refs, way_id, sense):
    pairs = [(a, b) for a, b in zip(refs, refs[1:]) if a != b]
    if sense == "reverse":
        pairs = [(b, a) for a, b in pairs]
    for start, end in pairs:
        graph[start].append((end, way_id))
    if sense == "both":
        for start, end in pairs:
            graph[end].append((start, way_id))


def build_graph(items, points, include_unverified=False):
    graph = defaultdict(list)
    for item in items:
        sense = item["sense"]
        if sense is None and include_unverified:
            sense = "both"
        if sense is None:
            continue
        add_edges(graph, item["refs"], item["id"], sense)
    return graph


def path_between(graph, start, goal, banned):
    seen = {start}
    queue = deque([(start, [])])
    while queue:
        node, steps = queue.popleft()
        if node == goal and steps:
            return steps
        for nxt, way_id in graph[node]:
            if way_id in banned or nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, steps + [way_id]))
    return None


def unique(steps):
    ordered = []
    for way_id in steps or []:
        if not ordered or ordered[-1] != way_id:
            ordered.append(way_id)
    return ordered


def forward_offset(refs, start, goal):
    body = refs[:-1] if refs[0] == refs[-1] else list(refs)
    if start not in body or goal not in body:
        return None
    return (body.index(goal) - body.index(start)) % len(body)


def route_report(items, ways, points):
    by_id = {item["id"]: item for item in items}
    verified = build_graph(items, points, include_unverified=False)
    pedragosa = {item["id"] for item in items if item["street"] == "pedragosa"}
    del_mar = {item["id"] for item in items if item["street"] == "delmar"}
    through_steps = path_between(verified, ORIGIN, DESTINATION, pedragosa | del_mar)
    through_ways = unique(through_steps)
    through_legal = bool(
        through_ways
        and RING in through_ways
        and PARADA5 in through_ways
        and not (set(through_ways) & (pedragosa | del_mar))
    )
    ring_refs = ways[RING][1]
    entry = ways["100089295"][1][-1]
    exit_node = ways["29235087"][1][0]
    arc = forward_offset(ring_refs, entry, exit_node)
    parada_arc = forward_offset(ways[PARADA5][1], ways["983235081"][1][-1], ways["100089295"][1][0])
    if through_legal and (arc in (None, 0) or parada_arc in (None, 0)):
        through_legal = False
    avoid_steps = path_between(verified, ORIGIN, DESTINATION, {RING})
    avoid_ways = unique(avoid_steps)
    avoid_legal = bool(avoid_ways and RING not in avoid_ways and (set(avoid_ways) & pedragosa) and (set(avoid_ways) & del_mar))
    diagnostic_graph = build_graph(items, points, include_unverified=True)
    diagnostic_steps = path_between(diagnostic_graph, ORIGIN, DESTINATION, {RING})
    diagnostic_ways = unique(diagnostic_steps)
    unverified_ids = {item["id"] for item in items if not item["verified"]}
    used_unverified = [way_id for way_id in diagnostic_ways if way_id in unverified_ids]
    diagnostic_connects = bool(
        diagnostic_ways
        and RING not in diagnostic_ways
        and (set(diagnostic_ways) & pedragosa)
        and (set(diagnostic_ways) & del_mar)
        and used_unverified
    )
    blocked = []
    for way_id in sorted(unverified_ids, key=int):
        item = by_id[way_id]
        blocked.append({
            "id": way_id,
            "name": item["data"].get("name"),
            "oneway": item["data"].get("oneway"),
            "lanes": item["data"].get("lanes"),
            "from": item["refs"][0],
            "to": item["refs"][-1],
            "usedByDiagnostic": way_id in used_unverified,
        })
    return {
        "origin": {"node": ORIGIN, "place": "Artigas en el cruce con Francia"},
        "destination": {"node": DESTINATION, "place": "Empalme de Artigas y Avenida del Mar"},
        "through": {
            "legal": through_legal,
            "ways": through_ways if through_legal else [],
            "ringArcNodes": arc,
            "paradaArcNodes": parada_arc,
        },
        "avoid": {
            "legal": avoid_legal,
            "ways": avoid_ways if avoid_legal else [],
            "diagnosticConnects": diagnostic_connects,
            "diagnosticAccepted": False,
            "blockedBy": blocked,
        },
    }


def francia_gap(items, nodes, points):
    artigas = {ref for item in items if item["street"] == "artigas" for ref in item["refs"]}
    distance, node = min((meters(points[FRANCIA_END], points[other]), other) for other in artigas)
    return {
        "joinsArtigasToPedragosa": False,
        "openEnd": FRANCIA_END,
        "nearestArtigasNode": node,
        "gapMeters": round(distance, 1),
        "detail": (
            "Avenida Francia no forma un tramo vehicular continuo entre Artigas y Pedragosa: "
            f"el extremo {FRANCIA_END} queda a {distance:.0f} m del nodo de Artigas más cercano."
        ),
    }


def control_nodes(items, nodes):
    used = {ref for item in items for ref in item["refs"]}
    signals, yields = [], []
    for node_id in sorted(used, key=int):
        info = tags(nodes[node_id])
        if info.get("highway") == "traffic_signals":
            signals.append(node_id)
        elif info.get("highway") in {"give_way", "stop"}:
            yields.append({"id": node_id, "highway": info["highway"]})
    return signals, yields


def legend():
    return [{"street": key, "label": label, "color": color} for key, (label, color) in LABELS.items()]


def build_notes(routes, francia, rings):
    blocked = [item["id"] for item in routes["avoid"]["blockedBy"]]
    ring = next(item for item in rings if item["id"] == RING)
    notes = []
    if routes["through"]["legal"] and ring["accepted"]:
        notes.append(
            "El recorrido por la rotonda sale de Artigas en Francia, cruza Parada 5 y el anillo, "
            "y llega al empalme de Artigas con Avenida del Mar. El anillo está cerrado y recorrido en sentido antihorario, "
            "de acuerdo con los accesos de sentido explícito."
        )
    notes.append(
        "El desvío por Pedragosa Sierra y Avenida del Mar depende de las vías "
        + " y ".join(blocked)
        + ". Ninguna trae oneway. Ese sentido no entra a la red transitable."
    )
    if routes["avoid"]["diagnosticConnects"]:
        notes.append(
            "Recorridas en ambos sentidos, esas vías conectarían el desvío dentro del recorte. "
            "El caso no acepta ese sentido y no lo simula."
        )
    else:
        notes.append(
            "Recorridas en ambos sentidos, esas vías tampoco unen el origen con el destino dentro del recorte."
        )
    notes.append(francia["detail"])
    notes.append(
        "Las vías sin maxspeed o sin carriles quedan con el valor de tipo de SUMO. "
        "Ese valor es un predeterminado del compilador."
    )
    notes.append(
        "Los giros tomados del snapshot son las relaciones restriction incluidas en el recorte. "
        "La compilación activa no-turnarounds para no agregar giros en U."
    )
    notes.append(
        "Los semáforos son los nodos highway=traffic_signals del snapshot. "
        "El programa horario es el estático de SUMO."
    )
    notes.append("Las colas por acceso quedan sin medir: la comparación se detuvo antes de simular.")
    return notes


def pending_observations():
    return [
        "El pico de las 18:00 a 20:00 en temporada alta sigue sin aforos, giros medidos ni horarios de ómnibus.",
        "La rotonda no tiene nombre en el snapshot. Novillo Alegre y la Parada 8 identifican el lugar por una dirección comercial externa.",
        "Queda pendiente de validar si la rotonda reparte la congestión entre Roosevelt y Artigas.",
    ]


def verify():
    _attributes, nodes, points, ways, _relations = regional_network()
    missing = [way_id for way_id in WAYS if way_id not in ways]
    if missing:
        raise NovilloError(f"Faltan vías del recorte aprobado: {', '.join(missing)}.")
    check_anchors(ways)
    rings = [ring_report(way_id, ways, points) for way_id in RINGS]
    items = mark_verified(clip_items(ways), rings)
    routes = route_report(items, ways, points)
    francia = francia_gap(items, nodes, points)
    signals, yields = control_nodes(items, nodes)
    main_ring = next(item for item in rings if item["id"] == RING)
    comparison = None
    if not main_ring["accepted"] or not routes["through"]["legal"] or routes["avoid"]["legal"]:
        comparison = None
    blocked_ids = [item["id"] for item in routes["avoid"]["blockedBy"]]
    summary = (
        "La comparación quedó detenida. El desvío por Pedragosa Sierra y Avenida del Mar "
        f"depende de las vías {' y '.join(blocked_ids)}, sin sentido explícito."
    )
    return {
        "stage": "1G.1",
        "experimental": True,
        "calibrated": False,
        "seasonal": False,
        "comparison": comparison,
        "simulated": None,
        "queues": {"measured": False, "reason": "La comparación se detuvo antes de simular."},
        "summary": summary,
        "roundabouts": [{key: item[key] for key in (
            "id", "name", "closed", "counterclockwise", "accepted", "entries", "exits",
            "unverifiedApproaches", "contradictions", "review", "oneway", "lanes", "maxspeed",
        )} for item in rings],
        "routes": routes,
        "francia": {key: francia[key] for key in ("joinsArtigasToPedragosa", "openEnd", "nearestArtigasNode", "gapMeters")},
        "blockage": {
            "comparison": True,
            "summary": summary,
            "ways": routes["avoid"]["blockedBy"],
        },
        "mappedSignals": signals,
        "yieldNodes": yields,
        "notes": build_notes(routes, francia, rings),
        "pendingLocalObservations": pending_observations(),
        "legend": legend(),
        "turns": {
            "source": "relaciones restriction del snapshot cuyos miembros están en el recorte",
            "noTurnarounds": True,
            "turnLanesImported": False,
        },
    }


def used_nodes(items):
    return {ref for item in items for ref in item["refs"]}


def copy_node(node):
    element = ET.Element("node", id=node.get("id"), lat=node.get("lat"), lon=node.get("lon"))
    for tag in node.findall("tag"):
        ET.SubElement(element, "tag", k=tag.get("k"), v=tag.get("v"))
    return element


def copy_way(item):
    element = ET.Element("way", id=item["id"])
    for ref in item["refs"]:
        ET.SubElement(element, "nd", ref=ref)
    for tag in item["element"].findall("tag"):
        ET.SubElement(element, "tag", k=tag.get("k"), v=tag.get("v"))
    return element


def copy_relation(relation):
    element = ET.Element("relation", id=relation.get("id"))
    for member in relation.findall("member"):
        ET.SubElement(element, "member", type=member.get("type"), ref=member.get("ref"), role=member.get("role") or "")
    for tag in relation.findall("tag"):
        ET.SubElement(element, "tag", k=tag.get("k"), v=tag.get("v"))
    return element


def restrictions_for(relations, way_ids, node_ids):
    kept = []
    for relation in relations:
        if tags(relation).get("type") != "restriction":
            continue
        members = relation.findall("member")
        way_members = [member.get("ref") for member in members if member.get("type") == "way"]
        node_members = [member.get("ref") for member in members if member.get("type") == "node"]
        if way_members and set(way_members) <= way_ids and set(node_members) <= node_ids:
            kept.append(relation)
    return kept


def write_osm(path, nodes, items, relations):
    node_ids = used_nodes(items)
    way_ids = {item["id"] for item in items}
    chosen_nodes = [nodes[node_id] for node_id in sorted(node_ids, key=int)]
    lons = [float(node.get("lon")) for node in chosen_nodes]
    lats = [float(node.get("lat")) for node in chosen_nodes]
    root = ET.Element("osm", version="0.6", generator="urbanflow-etapa1g1")
    ET.SubElement(
        root, "bounds",
        minlon=f"{min(lons):.7f}", minlat=f"{min(lats):.7f}",
        maxlon=f"{max(lons):.7f}", maxlat=f"{max(lats):.7f}",
    )
    for node in chosen_nodes:
        root.append(copy_node(node))
    for item in sorted(items, key=lambda current: int(current["id"])):
        root.append(copy_way(item))
    kept = restrictions_for(relations, way_ids, node_ids)
    for relation in sorted(kept, key=lambda current: int(current.get("id"))):
        root.append(copy_relation(relation))
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return [relation.get("id") for relation in kept]


def locate_netconvert():
    portable = ROOT / "results/baseline-v001-tools/portable/sumo-1.26.0"
    executable = portable / "bin/netconvert.exe"
    if not executable.is_file() or file_sha256(executable) != NETCONVERT_SHA256:
        raise NovilloError("netconvert no es el binario portable 1.26.0. No se instaló otro.")
    environment = os.environ.copy()
    environment["SUMO_HOME"] = str(portable)
    return str(executable), environment


def compile_network(directory):
    executable, environment = locate_netconvert()
    command = [
        executable,
        "--osm-files", "red-verificada.osm.xml",
        "--output-file", "red.net.xml",
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
    ]
    result = subprocess.run(command, cwd=directory, env=environment, capture_output=True, text=True, timeout=90)
    log = directory / "netconvert.log"
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise NovilloError("netconvert falló. El detalle quedó en netconvert.log.")
    return directory / "red.net.xml"


def edge_way(edge_id):
    return edge_id.split("#", 1)[0].lstrip("-")


def lane_speed(edge):
    lane = edge.find("lane")
    return None if lane is None else lane.get("speed")


def inspect_network(path, items):
    root = ET.parse(path).getroot()
    edges = [edge for edge in root.findall("edge") if edge.get("function") != "internal"]
    present = {edge_way(edge.get("id")) for edge in edges}
    unverified = sorted((item["id"] for item in items if not item["verified"]), key=int)
    leaked = [way_id for way_id in unverified if way_id in present]
    missing_speed = []
    missing_lanes = []
    kept_speed = []
    for item in items:
        if not item["verified"] or item["id"] not in present:
            continue
        if item["data"].get("maxspeed"):
            kept_speed.append(item["id"])
        else:
            missing_speed.append(item["id"])
        if not item["data"].get("lanes"):
            missing_lanes.append(item["id"])
    examples = []
    for edge in edges:
        way_id = edge_way(edge.get("id"))
        if way_id in {RING, "29235087"} and way_id not in {item["way"] for item in examples}:
            examples.append({
                "way": way_id,
                "edge": edge.get("id"),
                "laneSpeed": lane_speed(edge),
                "priority": edge.get("priority"),
                "type": edge.get("type"),
                "lanes": len(edge.findall("lane")),
            })
    ring_edges = [edge for edge in edges if edge_way(edge.get("id")) == RING]
    ring_lengths = [float(edge.find("lane").get("length")) for edge in ring_edges if edge.find("lane") is not None]
    entries = []
    for connection in root.findall("connection"):
        if edge_way(connection.get("from", "")) == "100089295" and edge_way(connection.get("to", "")) == RING:
            entries.append({"from": connection.get("from"), "to": connection.get("to"), "dir": connection.get("dir"), "state": connection.get("state")})
    programs = [{"id": logic.get("id"), "type": logic.get("type")} for logic in root.findall("tlLogic")]
    return {
        "edges": len(edges),
        "ringPresent": RING in present,
        "paradaPresent": PARADA5 in present,
        "unverifiedPresent": leaked,
        "excludedPresent": sorted((way_id for way_id in EXCLUDED if way_id in present), key=int),
        "waysWithMappedSpeed": sorted(kept_speed, key=int),
        "waysWithSumoDefaultSpeed": sorted(missing_speed, key=int),
        "waysWithSumoDefaultLanes": sorted(missing_lanes, key=int),
        "examples": examples,
        "ringLengthMeters": round(sum(ring_lengths), 1),
        "ringEdgesShorterThanOneMeter": sum(length < 1 for length in ring_lengths),
        "artigasEntry": entries,
        "signalPrograms": programs,
        "prioritySource": "clase highway del tipo SUMO; el estado del enlace lo asigna netconvert",
        "speedSource": "maxspeed de OSM cuando existe; si no, el tipo SUMO",
        "signalProgram": "estático de SUMO donde el nodo etiquetado quedó como cruce",
    }


def geojson(items, points):
    features = []
    longest = {}
    for item in items:
        coordinates = [[round(points[ref][0], 6), round(points[ref][1], 6)] for ref in item["refs"]]
        features.append({
            "type": "Feature",
            "properties": {
                "osmWay": item["id"],
                "name": item["data"].get("name"),
                "street": item["street"],
                "label": item["label"],
                "color": item["color"],
                "verified": item["verified"],
            },
            "geometry": {"type": "LineString", "coordinates": coordinates},
        })
        length = sum(meters(points[a], points[b]) for a, b in zip(item["refs"], item["refs"][1:]))
        current = longest.get(item["label"])
        if current is None or length > current[0]:
            longest[item["label"]] = (length, coordinates[len(coordinates) // 2], item)
    for label, (_length, coordinate, item) in longest.items():
        features.append({
            "type": "Feature",
            "properties": {
                "label": label,
                "street": item["street"],
                "color": item["color"],
                "verified": True,
            },
            "geometry": {"type": "Point", "coordinates": coordinate},
        })
    return {"type": "FeatureCollection", "features": features}


def assert_clip_bounds(path, nodes):
    root = ET.parse(path).getroot()
    way_ids = {way.get("id") for way in root.findall("way")}
    node_ids = {node.get("id") for node in root.findall("node")}
    leaked = sorted((way_id for way_id in EXCLUDED if way_id in way_ids), key=int)
    if leaked or "1156780611" in node_ids:
        raise NovilloError(f"El recorte incluye geometría fuera del alcance: {leaked or '1156780611'}.")
    if RING not in way_ids or PARADA5 not in way_ids:
        raise NovilloError("El recorte perdió la rotonda o Parada 5.")
    return {"ways": len(way_ids), "nodes": len(node_ids)}


def write_report(report):
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(payload, encoding="utf-8")
    return payload


def main():
    snapshot = ROOT / SNAPSHOT
    if file_sha256(snapshot) != "868b473a814999649af1d03ba164be232320c9dd82a229d5514315c0afc3a272":
        raise NovilloError("El snapshot OSM cambió. No se compiló otro recorte.")
    report = verify()
    if report["routes"]["avoid"]["legal"] or report["comparison"] is not None:
        raise NovilloError("La comprobación aceptó un desvío que esta etapa no debe simular sin sentido explícito.")
    if not report["routes"]["through"]["legal"]:
        report["blockage"]["summary"] = "La comparación quedó detenida. El recorrido por la rotonda no quedó verificado."
        report["summary"] = report["blockage"]["summary"]
    _attributes, nodes, points, ways, relations = regional_network()
    items = mark_verified(clip_items(ways), report["roundabouts"])
    cleanup_temporary(ROOT, STAGE)
    directory = temporary_directory(ROOT, STAGE)
    write_hash_reference(directory, snapshot, "snapshot.ref.json")
    clip = directory / "recorte.osm.xml"
    verified = directory / "red-verificada.osm.xml"
    report["restrictions"] = {
        "clip": write_osm(clip, nodes, items, relations),
        "verified": write_osm(verified, nodes, [item for item in items if item["verified"]], relations),
    }
    report["clip"] = assert_clip_bounds(clip, nodes)
    network = compile_network(directory)
    report["network"] = inspect_network(network, items)
    network_report = report["network"]
    if network_report["unverifiedPresent"] or network_report["excludedPresent"] or not network_report["ringPresent"]:
        raise NovilloError("La red compilada no respeta el recorte verificado.")
    missing_route = [way_id for way_id in report["routes"]["through"]["ways"] if way_id not in {
        edge_way(edge.get("id")) for edge in ET.parse(network).getroot().findall("edge")
    }]
    if missing_route:
        raise NovilloError(f"La red compilada perdió vías del recorrido verificado: {', '.join(missing_route)}.")
    by_way = {item["way"]: item for item in network_report["examples"]}
    compiled_signals = {item["id"] for item in network_report["signalPrograms"]}
    network_report["signalsKeptAsPrograms"] = sorted(set(report["mappedSignals"]) & compiled_signals, key=int)
    network_report["signalsWithoutProgram"] = sorted(set(report["mappedSignals"]) - compiled_signals, key=int)
    mapped = by_way.get("29235087", {}).get("laneSpeed")
    default_speed = by_way.get(RING, {}).get("laneSpeed")
    network_report["notes"] = [
        f"Artigas 29235087 trae maxspeed 60 y el carril compilado queda en {mapped} m/s.",
        f"El anillo no trae maxspeed. El tipo secondary de SUMO le asigna {default_speed} m/s.",
        (
            f"El anillo compilado suma {network_report['ringLengthMeters']} m en tramos visibles y "
            f"{network_report['ringEdgesShorterThanOneMeter']} miden menos de 1 m. "
            "El mapa usa la geometría del snapshot."
        ),
    ]
    collection = geojson(items, points)
    GEOJSON.write_text(json.dumps(collection, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = write_report(report)
    (directory / "caso.json").write_text(payload, encoding="utf-8")
    print(json.dumps({
        "summary": report["summary"],
        "through": report["routes"]["through"]["legal"],
        "avoid": report["routes"]["avoid"]["legal"],
        "diagnosticConnects": report["routes"]["avoid"]["diagnosticConnects"],
        "stageBytes": directory_bytes(directory),
        "publicBytes": PUBLIC.stat().st_size + GEOJSON.stat().st_size,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
