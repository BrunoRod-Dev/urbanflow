"""Build a reproducible SUMO study for an OpenStreetMap junction."""

from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import gettempdir
import time
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from .export_web import fcd_frames, locate_sumo
from .lane_geometry import replay_geometry, reversed_straights
from .regional_map import write_local_extract
from .signal_replay import prepare_signal_recording, signal_replay


FETCH_RADIUS = 460
STUDY_RADIUS = 325
SNAP_DISTANCE = 55
DURATION = 240
MAX_TRIPS = 10_000
DRAIN_SECONDS = 60
SEED = 42
MAX_OSM_SIZE = 8 * 1024 * 1024
VEHICLE_TYPES = {
    'car': {'vClass': 'passenger', 'length': 5, 'width': 1.8, 'height': 1.5},
    'bus': {'vClass': 'bus', 'length': 12, 'width': 2.5, 'height': 3.4},
    'terminal-bus': {'vClass': 'bus', 'length': 8.54, 'width': 2.55, 'height': 3},
    'motorcycle': {'vClass': 'motorcycle', 'length': 2.2, 'width': .9, 'height': 1.5,
                   'accel': 3.5, 'decel': 5, 'minGap': 1.5, 'maxSpeed': 25},
    'pickup': {'vClass': 'passenger', 'length': 5.3, 'width': 1.9, 'height': 1.85,
               'accel': 2.2, 'decel': 4.5, 'minGap': 2.5, 'maxSpeed': 33.33},
}
VEHICLE_LENGTHS = {kind: spec['length'] for kind, spec in VEHICLE_TYPES.items()}
VEHICLE_LABELS = {'bus': 'ómnibus', 'terminal-bus': 'ómnibus', 'motorcycle': 'moto', 'pickup': 'camioneta'}
SAMPLE_FLEET = {'terminal-bus': 1, 'motorcycle': 2, 'pickup': 2}
MOTOR_ROADS = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
    'residential', 'service', 'living_street', 'road',
    'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
}


class StudyError(Exception):
    pass


def bounds_at(lon, lat, radius):
    dy = radius / 111_320
    dx = dy / math.cos(math.radians(lat))
    return [round(value, 6) for value in (lon - dx, lat - dy, lon + dx, lat + dy)]


def distance(point, center):
    east = (point[0] - center[0]) * math.cos(math.radians(center[1]))
    return 111_320 * math.hypot(east, point[1] - center[1])


def download_osm(lon, lat, destination, cache):
    bounds = bounds_at(round(lon, 4), round(lat, 4), FETCH_RADIUS)
    region = write_local_extract(bounds, destination)
    if region:
        return region['source'], bounds, region
    query = ','.join(f'{value:.6f}' for value in bounds)
    source = f'https://api.openstreetmap.org/api/0.6/map?bbox={query}'
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / f'{query}.osm.xml'
    try:
        if cached.is_file() and time.time() - cached.stat().st_mtime < 24 * 3600:
            data = cached.read_bytes()
        else:
            request = Request(source, headers={'User-Agent': 'UrbanFlow local traffic study/1.0'})
            with urlopen(request, timeout=20) as response:
                data = response.read(MAX_OSM_SIZE + 1)
            if len(data) > MAX_OSM_SIZE or ET.fromstring(data).tag != 'osm':
                raise StudyError('OpenStreetMap devolvió un recorte inesperado.')
            cached.write_bytes(data)
    except (OSError, ET.ParseError) as error:
        raise StudyError('No se pudo descargar el recorte de OpenStreetMap. Revisá la conexión o reintentá.') from error
    destination.write_bytes(data)
    return source, bounds, None


def tags(element):
    return {tag.get('k'): tag.get('v') for tag in element.findall('tag')}


def junction_candidates(points, ways):
    neighbors = defaultdict(set)
    ring_neighbors = defaultdict(set)
    access_names = defaultdict(set)
    for way in ways:
        info = tags(way)
        if info.get('highway') not in MOTOR_ROADS or info.get('area') == 'yes':
            continue
        access = info.get('motorcar', info.get('motor_vehicle', info.get('access')))
        if access in {'private', 'no'} and info.get('bus') not in {'yes', 'designated'}:
            continue
        refs = [node.get('ref') for node in way.findall('nd') if node.get('ref') in points]
        for first, second in zip(refs, refs[1:]):
            neighbors[first].add(second)
            neighbors[second].add(first)
            if info.get('junction') == 'roundabout':
                ring_neighbors[first].add(second)
                ring_neighbors[second].add(first)
            else:
                name = info.get('name', 'Vía sin nombre')
                access_names[first, second].add(name)
                access_names[second, first].add(name)

    def candidate(center, nodes, ring):
        arms = [(node, adjacent) for node in sorted(nodes) for adjacent in sorted(neighbors[node] - nodes)]
        accesses = sorted({name for arm in arms for name in access_names[arm]})
        roads = [name for name in accesses if name != 'Vía sin nombre']
        label = ' y '.join(name.removeprefix('Avenida ') for name in roads[:2])
        kind = 'Rotonda' if ring else 'Cruce'
        return {
            'junctionId': f'{"r" if ring else "n"}{min(nodes, key=int)}',
            'title': f'{kind} de {label}' if label else f'{kind} seleccionado',
            'location': center, 'osmNodes': sorted(nodes), 'roundabout': ring,
            'bounds': bounds_at(*center, STUDY_RADIUS), 'accesses': accesses,
            'accessLines': [[points[node], points[adjacent]] for node, adjacent in arms],
        }

    candidates = []
    remaining = set(ring_neighbors)
    while remaining:
        seed = remaining.pop()
        group = {seed}
        stack = [seed]
        while stack:
            attached = ring_neighbors[stack.pop()] & remaining
            remaining -= attached
            group.update(attached)
            stack.extend(attached)
        if len(group) >= 3 and any(neighbors[node] - group for node in group):
            center = tuple(sum(points[node][i] for node in sorted(group)) / len(group) for i in (0, 1))
            candidates.append(candidate(center, group, True))

    for node, adjacent in neighbors.items():
        if len(adjacent) >= 3 and node not in ring_neighbors:
            candidates.append(candidate(points[node], {node}, False))
    return candidates


def nearby_junctions(candidates, points, clicked):
    nearby = []
    for target in candidates:
        anchors = [target['location'], *(points[node] for node in target['osmNodes'])] if target['roundabout'] else [target['location']]
        score = min(distance(point, clicked) for point in anchors)
        if score <= SNAP_DISTANCE:
            nearby.append((score, not target['roundabout'], target['junctionId'], target))
    return [{**target, 'distanceMeters': round(score)} for score, _, _, target in sorted(nearby)]


def identify_junction(osm, clicked):
    points = {node.get('id'): (float(node.get('lon')), float(node.get('lat'))) for node in osm.findall('node')}
    candidates = nearby_junctions(junction_candidates(points, osm.findall('way')), points, clicked)
    if not candidates:
        raise StudyError('No encontramos un cruce vehicular a menos de 55 m. Marcá un punto más cerca de la intersección.')
    return candidates[0]


def sumo_tools():
    sumo, netconvert = locate_sumo(), locate_sumo('netconvert')
    env = os.environ.copy()
    if sumo and netconvert:
        return sumo, netconvert, env
    executable = '.exe' if os.name == 'nt' else ''
    package = importlib.util.find_spec('sumo')
    homes = [Path(package.origin).parent] if package and package.origin else []
    if os.name == 'nt':
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            if env.get(variable):
                homes.append(Path(env[variable]) / 'Eclipse Sumo')
        homes.append(Path(gettempdir()) / 'urbanflow-sumo-runtime' / 'sumo')
    for home in homes:
        sumo = home / 'bin' / f'sumo{executable}'
        netconvert = home / 'bin' / f'netconvert{executable}'
        if sumo.is_file() and netconvert.is_file():
            env['SUMO_HOME'] = str(home)
            return str(sumo), str(netconvert), env
    raise StudyError('SUMO no está disponible. Instalá SUMO o configurá SUMO_HOME y volvé a intentar.')


def run_tool(arguments, directory, env, stage):
    try:
        result = subprocess.run(arguments, cwd=directory, env=env, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=90)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise StudyError(f'{stage} no pudo completarse. Revisá la instalación de SUMO e intentá otra vez.') from error
    with (directory / 'sumo.log').open('a', encoding='utf-8') as log:
        log.write(f'{stage}\n{result.stdout}{result.stderr}\n')
    if result.returncode:
        raise StudyError(f'{stage} falló. Los detalles quedaron en sumo.log del estudio.')


def permits(lane, vclass):
    allowed = lane.get('allow', 'all').split()
    denied = lane.get('disallow', '').split()
    return ('all' in allowed or vclass in allowed) and 'all' not in denied and vclass not in denied


@dataclass(frozen=True)
class Edge:
    origin: str
    destination: str
    length: float
    kind: str
    name: str


def read_network(network, vclass):
    edges = {}
    lanes = {}
    forward, reverse = defaultdict(set), defaultdict(set)
    for edge in network.findall('edge[@from]'):
        valid = [lane for lane in edge.findall('lane') if permits(lane, vclass)]
        if valid:
            edge_id = edge.get('id')
            lanes[edge_id] = {lane.get('index') for lane in valid}
            edges[edge_id] = Edge(edge.get('from'), edge.get('to'), float(valid[0].get('length')),
                                  edge.get('type', ''), edge.get('name', ''))
    for connection in network.findall('connection'):
        first, second = connection.get('from'), connection.get('to')
        if (connection.get('fromLane') in lanes.get(first, ())
                and connection.get('toLane') in lanes.get(second, ()) and permits(connection, vclass)):
            forward[first].add(second)
            reverse[second].add(first)
    return edges, forward, reverse


def paths_from(start, graph, edges, blocked, limit):
    queue = [(0, (start,))]
    settled = {}
    while queue:
        length, path = heappop(queue)
        edge = path[-1]
        if edge in settled:
            continue
        settled[edge] = (length, path)
        for other in graph[edge] - blocked:
            total = length + edges[other].length
            if other not in settled and total <= limit:
                heappush(queue, (total, path + (other,)))
    return settled


def extent_paths(start, graph, edges, blocked):
    paths = paths_from(start, graph, edges, blocked, 410)

    def pick(candidates):
        return min(candidates.values(), key=lambda item: (abs(item[0] - 185), item[1]))[1]

    choices = [pick({edge: path for edge, path in paths.items() if edges[edge].length >= 18} or paths)]
    branches = sorted((length, edge, path) for edge, (length, path) in paths.items() if edge != start
                      and length <= 215 and (edges[edge].kind.endswith('_link') or edges[edge].kind == 'highway.service'))
    for _, branch, path in branches[:8]:
        extension = paths_from(branch, graph, edges, blocked | set(path[:-1]), 260)
        candidates = {edge: result for edge, result in extension.items() if edges[edge].length >= 18}
        choices.append(path + pick(candidates or extension)[1:])
    return list(dict.fromkeys(choices))


def target_nodes(network, target):
    osm_nodes = set(target['osmNodes'])
    if target['roundabout']:
        rings = [set(ring.get('nodes').split()) for ring in network.findall('roundabout')]
        if rings:
            match = max(rings, key=lambda nodes: len(nodes & osm_nodes))
            if match & osm_nodes:
                return match
    return osm_nodes & {junction.get('id') for junction in network.findall('junction')}


def find_routes(network, target, vclass):
    edges, forward, reverse = read_network(network, vclass)
    nodes = target_nodes(network, target)
    entering = sorted(key for key, edge in edges.items() if edge.destination in nodes and edge.origin not in nodes)
    leaving = sorted(key for key, edge in edges.items() if edge.origin in nodes and edge.destination not in nodes)
    inside = {key for key, edge in edges.items() if edge.origin in nodes and edge.destination in nodes}
    blocked = set(entering + leaving) | inside
    exits = {key: extent_paths(key, forward, edges, blocked) for key in leaving}
    routes = {}
    for entry in entering:
        ingresses = extent_paths(entry, reverse, edges, blocked)
        movements = paths_from(entry, forward, edges, set(edges) - inside - set(leaving), 500)
        for exit_edge in leaving:
            if exit_edge not in movements or edges[exit_edge].destination == edges[entry].origin:
                continue
            transit = movements[exit_edge][1][1:-1]
            for upstream, downstream in [(path, exits[exit_edge][0]) for path in ingresses] + [
                (ingresses[0], path) for path in exits[exit_edge][1:]
            ]:
                route = upstream[::-1] + transit + downstream
                if len(route) == len(set(route)):
                    routes[route] = (entry, exit_edge)
    return edges, routes


def group_movements(network, edges, samples):
    junctions = {node.get('id'): (float(node.get('x')), float(node.get('y'))) for node in network.findall('junction')}
    directions = ('N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO')

    def side_name(edge_id, outgoing=False):
        edge = edges[edge_id]
        start, end = junctions[edge.origin], junctions[edge.destination]
        outer, inner = (end, start) if outgoing else (start, end)
        angle = math.degrees(math.atan2(outer[0] - inner[0], outer[1] - inner[1]))
        side = directions[round(angle / 45) % 8]
        return f'{edge.name.removeprefix("Avenida ") or "Acceso"} · {side}'

    grouped = {}
    counts = {}
    for route, entry, exit_edge, kind, count in samples:
        key = (entry, exit_edge, kind)
        if key not in grouped:
            movement_id = f'{entry}:{exit_edge}:{kind}'
            origin = side_name(entry)
            destination = side_name(exit_edge, outgoing=True)
            qualifier = f' ({VEHICLE_LABELS[kind]})' if kind in VEHICLE_LABELS else ''
            grouped[key] = {'id': movement_id, 'label': f'{origin} → {destination}{qualifier}', 'from': origin,
                            'to': destination, 'entry': entry, 'kind': kind, 'routes': []}
            counts[movement_id] = 0
        movement = grouped[key]
        movement['routes'].append(route)
        counts[movement['id']] += count
    return list(grouped.values()), counts


def create_catalog(network, target):
    edges, routes = find_routes(network, target, 'passenger')
    bus_edges, bus_routes = find_routes(network, target, 'bus')
    # Cover accesses restricted to buses without inventing regular schedules.
    bus_only = {route: movement for route, movement in bus_routes.items() if any(edge not in edges for edge in route)}
    option_count = len(routes) + len(bus_only)
    if not option_count:
        raise StudyError('El cruce importado no tiene recorridos vehiculares conectados para simular. Probá un punto cercano.')
    per_route = max(2, min(8, round(50 / option_count)))
    samples = [(route, entry, exit_edge, 'car', per_route) for route, (entry, exit_edge) in routes.items()]
    samples += [(route, entry, exit_edge, 'bus', per_route) for route, (entry, exit_edge) in bus_only.items()]
    return group_movements(network, bus_edges | edges, samples)


def terminal_sample_movement(network, target, kind):
    if target.get('junctionId') != 'r1161502532':
        raise StudyError('La flota de muestra corresponde al estudio de Roosevelt y Camacho.')
    edges, routes = find_routes(network, target, VEHICLE_TYPES[kind]['vClass'])
    approach = ('230055789#7', '783169882#0', '553842606#1', '100473863#1')
    for route, (entry, exit_edge) in sorted(routes.items()):
        crosses_terminal = any(route[index:index + len(approach)] == approach for index in range(len(route)))
        if crosses_terminal and exit_edge == '100473841#0':
            movements, _ = group_movements(network, edges, [(route, entry, exit_edge, kind, 1)])
            return movements[0]
    raise StudyError(f'La red guardada no tiene un recorrido permitido para el tipo {VEHICLE_LABELS[kind]} desde la Terminal hasta Roosevelt.')


def traffic_details(catalog, counts, duration, source):
    return {'durationMinutes': duration, 'source': source, 'movements': [
        {**{key: movement[key] for key in ('id', 'label', 'from', 'to')}, 'count': counts[movement['id']]}
        for movement in catalog
    ]}


def validate_traffic(traffic, catalog):
    if not isinstance(traffic, dict):
        raise StudyError('Enviá los datos del tránsito para simular.')
    duration = traffic.get('durationMinutes')
    if type(duration) is not int or not 1 <= duration <= 60:
        raise StudyError('La duración del conteo tiene que ser un número entero entre 1 y 60 minutos.')
    source = traffic.get('source')
    if source not in ('sample', 'observed'):
        raise StudyError('Elegí si los volúmenes son de muestra u observados.')
    counts = traffic.get('counts')
    if not isinstance(counts, dict) or counts.keys() != {movement['id'] for movement in catalog}:
        raise StudyError('Los movimientos del conteo no coinciden con la red. Volvé a abrir el estudio.')
    if any(type(count) is not int or count < 0 for count in counts.values()):
        raise StudyError('Ingresá un número entero de vehículos mayor o igual a cero en cada movimiento.')
    if not 1 <= sum(counts.values()) <= MAX_TRIPS:
        raise StudyError('Ingresá entre 1 y 10.000 vehículos en total para la simulación local.')
    return traffic_details(catalog, counts, duration, source)


def write_demand(catalog, traffic, destination):
    counts = {movement['id']: movement['count'] for movement in traffic['movements']}
    samples = []
    for movement in catalog:
        quotient, remainder = divmod(counts[movement['id']], len(movement['routes']))
        for index, route in enumerate(movement['routes']):
            count = quotient + (index < remainder)
            if count:
                samples.append((route, movement['kind'], count))

    root = ET.Element('routes')
    for kind, spec in VEHICLE_TYPES.items():
        ET.SubElement(root, 'vType', id=kind, **{key: str(value) for key, value in spec.items()})
    used = {edge for path, _, _ in samples for edge in path}
    for index, (path, _, _) in enumerate(samples):
        ET.SubElement(root, 'route', id=f'r{index}', edges=' '.join(path))
    start_spacing = min(.55, 2 / len(samples))
    for index, (_, kind, count) in enumerate(samples):
        ET.SubElement(root, 'flow', id=f'f{index}', type=kind, route=f'r{index}',
                      begin=f'{index * start_spacing:.2f}', end=str(traffic['durationMinutes'] * 60), number=str(count),
                      departLane='best', departSpeed='max')
    ET.indent(root)
    ET.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)
    return used


def feature_collection(features):
    return {'type': 'FeatureCollection', 'features': features}


def map_network(directory, used):
    plain_edges = ET.parse(directory / 'map.edg.xml')
    features = []
    for edge in plain_edges.findall('edge'):
        edge_id = edge.get('id')
        for lane in edge.findall('lane'):
            coordinates = [[float(value) for value in point.split(',')[:2]] for point in lane.get('shape', '').split()]
            if len(coordinates) >= 2:
                features.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': coordinates},
                                 'properties': {'edge': edge_id, 'used': edge_id in used, 'name': edge.get('name', '')}})
    if not features:
        raise StudyError('La red de SUMO no se pudo proyectar sobre el mapa.')
    return feature_collection(features)


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temporary.replace(path)


def saved_catalog(directory, metadata):
    path = directory / 'traffic-catalog.json'
    try:
        if path.is_file():
            catalog = json.loads(path.read_text(encoding='utf-8'))
            counts = {movement['id']: movement['count'] for movement in metadata['traffic']['movements']}
            return catalog, counts

        network = ET.parse(directory / 'network.net.xml')
        demand = ET.parse(directory / 'routes.rou.xml')
        nodes = target_nodes(network, metadata)
        flows = demand.findall('flow')
        classes = {VEHICLE_TYPES.get(flow.get('type'), VEHICLE_TYPES['car'])['vClass'] for flow in flows}
        edges = {}
        for vclass in classes:
            edges.update(read_network(network, vclass)[0])
        paths = {route.get('id'): route.get('edges').split() for route in demand.findall('route')}
        samples = []
        for flow in flows:
            route = paths[flow.get('route')]
            entry = next(edge for edge in route if edges[edge].origin not in nodes and edges[edge].destination in nodes)
            exit_edge = next(edge for edge in route if edges[edge].origin in nodes and edges[edge].destination not in nodes)
            samples.append((route, entry, exit_edge, flow.get('type'), int(flow.get('number'))))
        if samples:
            return group_movements(network, edges, samples)
    except (KeyError, TypeError, ValueError, StopIteration, OSError, ET.ParseError) as error:
        raise StudyError('Este estudio guardado no tiene los datos necesarios para editar el tránsito. Generá uno nuevo desde el mapa.') from error
    raise StudyError('Este estudio guardado no tiene recorridos editables. Generá uno nuevo desde el mapa.')


def saved_traffic(directory, replay):
    """Supply the editable traffic summary for runs saved before the editor existed."""
    if 'traffic' in replay:
        return replay['traffic']
    catalog, counts = saved_catalog(directory, replay)
    duration = math.ceil(replay['seconds'] / 60)
    return traffic_details(catalog, counts, duration, 'sample')


def simulate_study(directory, sumo, env, target, catalog, traffic, seconds, update):
    used = write_demand(catalog, traffic, directory / 'routes.rou.xml')
    approaches = {movement['entry']: movement['from'] for movement in catalog}
    update('simulation', 'Simulando el tránsito con SUMO…', target)
    period = max(.5, math.ceil(seconds / 1_500 * 2) / 2)
    network = ET.parse(directory / 'network.net.xml')
    signal_args = prepare_signal_recording(network, directory)
    run_tool([sumo, '--net-file', 'network.net.xml', '--route-files', 'routes.rou.xml', '--end', str(seconds),
              '--step-length', '0.5', '--seed', str(SEED), '--time-to-teleport', '-1', '--no-step-log', 'true',
              '--fcd-output', 'trajectories.xml', '--fcd-output.geo', 'true', '--precision.geo', '7',
              '--device.fcd.period', str(period), '--summary-output', 'summary.xml', '--tripinfo-output', 'trips.xml',
              *signal_args],
             directory, env, 'La corrida de SUMO')
    summary = ET.parse(directory / 'summary.xml').getroot()[-1]
    if not int(summary.get('inserted', '0')):
        raise StudyError('SUMO no pudo ingresar vehículos en esta red. Revisá los movimientos y los volúmenes del escenario.')
    motion = replay_geometry(network, directory / 'map.nod.xml')
    vehicles = []
    frames = fcd_frames(directory / 'trajectories.xml', {'incoming': {key: key for key in approaches}},
                        geographic=True, vehicle_lengths=VEHICLE_LENGTHS if motion else None, vehicle_index=vehicles)
    geo_network = map_network(directory, used)
    diagnostics = {'reversedStraightConnections': reversed_straights(network)}
    write_json(directory / 'network-diagnostics.json', diagnostics)
    return {
        'seed': SEED, 'seconds': seconds, 'trips': sum(movement['count'] for movement in traffic['movements']),
        'arrived': int(summary.get('arrived')), 'inserted': int(summary.get('inserted')), 'usedEdges': sorted(used),
        'traffic': traffic, 'networkDiagnostics': diagnostics,
    }, {'network': geo_network, 'approaches': approaches, 'frames': frames, 'laneMotion': motion,
        'vehicleTypes': VEHICLE_TYPES, 'vehicleIndex': vehicles,
        'signalReplay': signal_replay(directory, network)}


def save_study(directory, metadata, output, catalog):
    write_json(directory / 'traffic-catalog.json', catalog)
    write_json(directory / 'metadata.json', metadata)
    replay = {**metadata, **output, 'source': 'sumo', 'geographic': True}
    write_json(directory / 'replay.json', replay)
    return replay


def build_network(directory, netconvert, env, target):
    bounds = ','.join(map(str, target['bounds']))
    command = [netconvert, '--osm-files', 'recorte.osm.xml', '--keep-edges.in-geo-boundary', bounds,
              '--keep-edges.by-vclass', 'passenger,bus', '--osm.turn-lanes', 'true', '--geometry.remove', 'true',
              '--tls.guess-signals', 'true', '--tls.join', 'true', '--tls.join-dist', '30',
              '--tls.default-type', 'actuated',
              '--no-turnarounds', 'true', '--output.street-names', 'true', '--output-file', 'network.net.xml',
              '--plain-output-prefix', 'map', '--proj.plain-geo', 'true', '--plain-output.lanes', 'true',
              '--precision.geo', '7']
    run_tool(command, directory, env, 'La conversión de calles')
    network = ET.parse(directory / 'network.net.xml')

    def is_camacho(connection):
        origin = connection['fromLane'].rsplit('_', 1)[0].split('#', 1)[0]
        destination = connection['toLane'].rsplit('_', 1)[0].split('#', 1)[0]
        return connection['junction'] == '1360039545' and origin == '-178119926' and destination == '121506103'

    if any(is_camacho(connection) for connection in reversed_straights(network)):
        patch = Path(__file__).resolve().parent / 'corrections' / 'camacho.nod.xml'
        run_tool(command + ['--node-files', str(patch)], directory, env, 'El ajuste del empalme de Camacho')
        network = ET.parse(directory / 'network.net.xml')
        if any(is_camacho(connection) for connection in reversed_straights(network)):
            raise StudyError('El empalme de Camacho conserva una inversión. Revisá la geometría de la red generada.')
    return network


def generate_study(directory, lon, lat, update, cache, osm_file=None, target=None):
    sumo, netconvert, env = sumo_tools()
    update('download', 'Cargando calles de OpenStreetMap…')
    extract = directory / 'recorte.osm.xml'
    if target is not None and osm_file is None:
        fetch_bounds = bounds_at(*target['location'], FETCH_RADIUS)
        region = write_local_extract(fetch_bounds, extract)
        if not region or region.get('snapshot') != target.get('snapshot'):
            raise StudyError('La base regional cambió desde que guardaste este estudio. Elegí el cruce de nuevo.')
        source = region['source']
    elif osm_file is None:
        source, fetch_bounds, region = download_osm(lon, lat, extract, cache)
    else:
        extract.write_bytes(Path(osm_file).read_bytes())
        source, fetch_bounds, region = 'Recorte de OpenStreetMap', None, None
    osm = ET.parse(extract)
    if target is None:
        target = identify_junction(osm, (lon, lat))
    elif not set(target['osmNodes']) <= {node.get('id') for node in osm.findall('node')}:
        raise StudyError('La red disponible cambió y ya no contiene el cruce guardado. Volvé a seleccionarlo para generar otro estudio.')
    update('network', 'Identificamos el cruce. Preparando la red vial…', target)
    network = build_network(directory, netconvert, env, target)
    catalog, counts = create_catalog(network, target)
    traffic = traffic_details(catalog, counts, DURATION // 60, 'sample')
    stats, output = simulate_study(directory, sumo, env, target, catalog, traffic, DURATION, update)
    imported = {feature['properties']['edge'].lstrip('-').split('#')[0] for feature in output['network']['features']}
    road_tags = [tags(way) for way in osm.findall('way') if way.get('id') in imported]
    no_lanes = sum(not any(info.get(key, '').isdecimal() and int(info[key]) > 0
                           for key in ('lanes', 'lanes:forward', 'lanes:backward')) for info in road_tags)
    no_speed = sum(not info.get('maxspeed') for info in road_tags)
    metadata = {
        **target, **stats, 'clicked': [lon, lat], 'osmSource': source, 'downloadBounds': fetch_bounds, 'regionalMap': region,
        'assumptions': [f'{no_lanes} vías sin carriles registrados y {no_speed} sin velocidad máxima explícita.',
                        'SUMO aplica valores de su tipo de vía y completa conexiones donde faltan datos.'],
    }
    return save_study(directory, metadata, output, catalog)


def rerun_study(directory, base_directory, traffic, update, *, sample_terminal_bus=False, sample_mixed_fleet=False):
    """Run edited counts on the saved road network and keep the source run intact."""
    try:
        base_metadata = json.loads((base_directory / 'metadata.json').read_text(encoding='utf-8'))
        catalog, _ = saved_catalog(base_directory, base_metadata)
    except (OSError, ValueError) as error:
        raise StudyError('No se pudo abrir la red del estudio guardado. Volvé a generarla desde el mapa.') from error
    if sample_terminal_bus or sample_mixed_fleet:
        if traffic['source'] != 'sample':
            raise StudyError('La flota de muestra se puede agregar a corridas con tráfico de muestra.')
        network = ET.parse(base_directory / 'network.net.xml')
        counts = dict(traffic['counts'])
        additions = SAMPLE_FLEET if sample_mixed_fleet else {'terminal-bus': 1}
        for kind, count in additions.items():
            movement = terminal_sample_movement(network, base_metadata, kind)
            if all(item['id'] != movement['id'] for item in catalog):
                catalog.append(movement)
            identifier = movement['id']
            if not sample_mixed_fleet or counts.get(identifier, 0) == 0:
                counts[identifier] = count
        traffic = {**traffic, 'counts': counts}
    traffic = validate_traffic(traffic, catalog)
    sumo, _, env = sumo_tools()
    target = {key: base_metadata[key] for key in ('title', 'location', 'osmNodes', 'roundabout', 'bounds')}
    update('network', 'Preparando el escenario con la red guardada…', target)
    try:
        for filename in ('network.net.xml', 'recorte.osm.xml', 'map.edg.xml'):
            shutil.copyfile(base_directory / filename, directory / filename)
        if (base_directory / 'map.nod.xml').is_file():
            shutil.copyfile(base_directory / 'map.nod.xml', directory / 'map.nod.xml')
    except OSError as error:
        raise StudyError('Faltan los archivos de la red guardada. Generá un nuevo estudio desde el mapa.') from error
    seconds = traffic['durationMinutes'] * 60 + DRAIN_SECONDS
    stats, output = simulate_study(directory, sumo, env, target, catalog, traffic, seconds, update)
    metadata = {**base_metadata, **stats}
    return save_study(directory, metadata, output, catalog)
