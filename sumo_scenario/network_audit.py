"""Audit the regional network and optional saved runs. Writes a JSON report."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from .lane_geometry import lane_shapes, reversed_straights
from .regional_map import coverage, write_local_extract
from .signal_replay import signal_links
from .street_scene import street_scene
from .study import VEHICLE_LENGTHS, build_network, permits, sumo_tools, tags, write_json


STORAGE_PROFILES = (('auto', 'car', 'passenger'), ('ómnibus de 8,54 m', 'terminal-bus', 'bus'),
                    ('ómnibus de 12 m', 'bus', 'bus'))


def issue(code, severity, reason, **fields):
    return {'code': code, 'severity': severity, 'reason': reason, **fields}


def signal_coverage(network, links, lane_nodes):
    """Inventory modeled permissions without treating the SUMO program as field evidence."""
    controllers = defaultdict(list)
    for link in links:
        controllers[link['controller']].append(link)
    programs = defaultdict(list)
    for logic in network.iterfind('tlLogic'):
        programs[logic.get('id')].append(logic)

    findings, inventory = [], []
    for controller, movements in sorted(controllers.items()):
        junctions = sorted({lane_nodes[link['fromLane']] for link in movements if link['fromLane'] in lane_nodes})
        definitions = programs[controller]
        inventory.append({'controller': controller, 'junctions': junctions,
                          'programSource': 'network.net.xml', 'fieldVerification': 'unverified',
                          'programs': [{'id': logic.get('programID'), 'type': logic.get('type'),
                                        'phases': [{'state': phase.get('state'), 'seconds': float(phase.get('duration'))}
                                                   for phase in logic.iterfind('phase')]}
                                       for logic in definitions], 'movements': movements})
        if not definitions:
            findings.append(issue('signal_program_missing', 'alert', 'El controlador no tiene un programa en la red.',
                                  controller=controller, junction=junctions[0] if junctions else None))
        for logic in definitions:
            states = [phase.get('state', '') for phase in logic.iterfind('phase')]
            for movement in movements:
                index = movement['index']
                context = {'junction': lane_nodes.get(movement['fromLane']), 'movement': movement,
                           'program': logic.get('programID')}
                if not states or any(index >= len(state) for state in states):
                    findings.append(issue('signal_state_missing', 'alert',
                                          'El programa no define el estado del movimiento en todas las fases.', **context))
                elif not any(state[index] in 'GgsOo' for state in states):
                    findings.append(issue('signal_movement_never_allowed', 'alert',
                                          'El movimiento conectado no recibe permiso en ninguna fase del programa.', **context))
    return inventory, findings


def signal_storage(network, links, lanes, lane_nodes):
    departures = defaultdict(list)
    for link in links:
        departures[link['fromLane']].append(link)
    phases = defaultdict(list)
    for program in network.iterfind('tlLogic'):
        phases[program.get('id')].extend(phase.get('state', '') for phase in program.iterfind('phase'))
    definitions = {lane.get('id'): lane for lane in network.iterfind('edge/lane')}
    connections = {(link.get('tl'), int(link.get('linkIndex')), f"{link.get('from')}_{link.get('fromLane')}",
                    f"{link.get('to')}_{link.get('toLane')}"): link
                   for link in network.iterfind('connection[@tl][@linkIndex]')}

    def connection(link):
        return connections[link['controller'], link['index'], link['fromLane'], link['toLane']]
    short_lanes = defaultdict(list)
    for entry in links:
        lane = entry['toLane']
        if lane not in lanes:
            continue
        storage = lanes[lane]['length']
        if storage >= max(VEHICLE_LENGTHS[kind] for _, kind, _ in STORAGE_PROFILES):
            continue
        for exit_link in departures[lane]:
            if exit_link['controller'] != entry['controller']:
                continue
            incoming, outgoing = entry['index'], exit_link['index']
            if not any(len(state) > max(incoming, outgoing) and state[incoming] in 'Gg' and state[outgoing] in 'rR'
                       for state in phases[entry['controller']]):
                continue
            elements = (definitions[entry['fromLane']], definitions[lane], definitions[exit_link['toLane']],
                        connection(entry), connection(exit_link))
            affected = [name for name, kind, vehicle_class in STORAGE_PROFILES if storage < VEHICLE_LENGTHS[kind] and all(
                permits(element, vehicle_class) for element in elements)]
            if not affected:
                continue
            short_lanes[lane].append(issue(
                'short_signal_storage', 'alert', 'El movimiento de entrada puede tener verde con la salida en rojo y el tramo intermedio no aloja el vehículo.',
                junction=lane_nodes.get(entry['fromLane']), movement=entry, nextMovement=exit_link,
                storageLane=lane, storageMeters=storage, vehicles=affected,
            ))
    return short_lanes


def stopped_in_signal(directory, links, short_lanes, lane_nodes, lane_lengths):
    fcd = directory / 'trajectories.xml'
    if not fcd.is_file():
        return []
    vias = {link['via']: link for link in links if link['via']}
    states = {}
    state_file = directory / 'signal-states.xml'
    if state_file.is_file():
        states = {(float(node.get('time')), node.get('id')): node.get('state', '')
                  for node in ET.parse(state_file).iterfind('tlsState')}
    active = {}
    stops = []
    pending_exits = defaultdict(list)

    def finish(key):
        stop = active.pop(key)
        duration = round(stop['last'] - stop['first'], 2)
        if duration >= 5:
            record = issue(
                'stopped_inside_signal', 'confirmed', 'La trayectoria registra una detención dentro de un enlace semaforizado o en un tramo corto entre señales.',
                junction=stop['junction'], vehicle=key[0], lane=key[1], vehicleType=stop['type'],
                movement=stop['movement'],
                firstSecond=stop['first'], lastSecond=stop['last'], durationSeconds=duration,
                entryStateAtStop=stop['entryState'],
                lanePositionMeters=stop['position'], laneLengthMeters=lane_lengths[key[1]],
            )
            stops.append(record)
            if stop['exits']:
                record['possibleExitIndices'] = [link['index'] for link in stop['exits']]
                pending_exits[key].append((record, stop['exits']))

    def state_at(link, time):
        if link:
            state = states.get((time, link['controller']), '')
            return state[link['index']:link['index'] + 1] or None
        return None

    events = ET.iterparse(fcd, events=('start', 'end'))
    _, root = next(events)
    recent = {}
    for event, frame in events:
        if event != 'end' or frame.tag != 'timestep':
            continue
        time = float(frame.get('time'))
        current = set()
        next_recent = {}
        transitions = []
        for vehicle in frame.iterfind('vehicle'):
            lane, vehicle_id = vehicle.get('lane'), vehicle.get('id')
            prior_lane, entered_from = recent.get(vehicle_id, (None, None))
            if prior_lane and prior_lane != lane:
                transitions.append(((vehicle_id, prior_lane), lane))
            entered_from = entered_from if prior_lane == lane else prior_lane
            next_recent[vehicle_id] = lane, entered_from
            if lane not in lane_lengths or float(vehicle.get('speed', 'inf')) >= .1:
                continue
            movement = vias.get(lane)
            exits = []
            junction = lane_nodes.get(movement['fromLane']) if movement else None
            if movement is None:
                candidates = [entry for entry in short_lanes.get(lane, [])
                              if entered_from in {entry['movement']['via'], entry['movement']['fromLane']}]
                if not candidates:
                    continue
                movement, junction = candidates[0]['movement'], candidates[0]['junction']
                exits = [entry['nextMovement'] for entry in candidates]
            key = vehicle_id, lane
            current.add(key)
            stop = active.setdefault(key, {
                'first': time, 'type': vehicle.get('type'), 'junction': junction,
                'movement': movement, 'exits': exits, 'entryState': state_at(movement, time),
                'position': float(vehicle.get('pos', '0')),
            })
            stop['last'] = time
        for key in active.keys() - current:
            finish(key)
        for key, next_lane in transitions:
            for record, exits in pending_exits.pop(key, []):
                observed = [link for link in exits if next_lane in (link['via'], link['toLane'])]
                if len(observed) == 1:
                    record.pop('possibleExitIndices')
                    record['nextMovement'] = observed[0]
                    record['exitStateAtStop'] = state_at(observed[0], record['firstSecond'])
        recent = next_recent
        root.remove(frame)
    for key in list(active):
        finish(key)
    return stops


def inspect_obstacles(network, street, lanes, lane_nodes, connections):
    from pyproj import Proj
    from shapely.geometry import LineString, Polygon
    from shapely.strtree import STRtree

    location = network.find('location')
    projection = Proj(location.get('projParameter'))
    offset = tuple(map(float, location.get('netOffset').split(',')))

    def local(point):
        return [value + shift for value, shift in zip(projection(*point), offset)]

    def geographic(point):
        return projection(*(value - shift for value, shift in zip(point, offset)), inverse=True)

    findings = []
    surfaces, polygons = [], []
    for surface in street['physicalSurfaces']:
        if surface.get('source') != 'OpenStreetMap' or not surface.get('id'):
            findings.append(issue('unbacked_obstacle', 'confirmed', 'El obstáculo carece de una referencia de origen.',
                                  surface=surface.get('id'), location=next(iter(surface['points']), None)))
            continue
        if surface['layer'] != '0':
            continue
        polygon = Polygon([local(point) for point in surface['points']])
        if not polygon.is_valid:
            findings.append(issue('invalid_surface', 'alert', 'El contorno mapeado no forma un polígono válido.',
                                  surface=surface['id'], location=surface['points'][0]))
            continue
        inner = polygon.buffer(-.25)
        if not inner.is_empty:
            surfaces.append(surface)
            polygons.append(inner)
    tree = STRtree(polygons)
    for identifier, lane in lanes.items():
        if len(lane['points']) < 2 or identifier in street['pedestrianLanes']:
            continue
        motion = connections.get(identifier, {})
        edges = [lane['edge']] if not motion else [lanes[link]['edge'] for link in motion.values() if link in lanes]
        if any(edge in street['edgeGrades'] for edge in edges):
            continue
        line = LineString(lane['points'])
        for index in tree.query(line):
            overlap = line.intersection(polygons[index])
            if overlap.length < .5:
                continue
            surface = surfaces[index]
            findings.append(issue(
                'trajectory_intersects_obstacle', 'confirmed', 'El eje de la trayectoria de SUMO atraviesa el interior de una superficie peatonal o un separador mapeado.',
                junction=lane_nodes.get(motion.get('fromLane', identifier)), movement=motion or {'lane': identifier},
                lane=identifier, surface=surface['id'], surfaceKind=surface['kind'], source=surface['source'],
                overlapMeters=round(overlap.length, 2), location=geographic(overlap.representative_point().coords[0]),
            ))
    return findings


def audit(directory, network=None, signals_only=False):
    if network is None:
        network = ET.parse(directory / 'network.net.xml')
    lane_nodes = {lane.get('id'): edge.get('to') for edge in network.iterfind('edge[@to]') for lane in edge.iterfind('lane')}
    links = signal_links(network)
    signal_inventory, signal_findings = signal_coverage(network, links, lane_nodes)
    if signals_only:
        return {'signalControllers': signal_inventory,
                'summary': dict(Counter(item['code'] for item in signal_findings)), 'issues': signal_findings}
    osm = ET.parse(directory / 'recorte.osm.xml')
    street = street_scene(directory, network, osm)
    lanes = lane_shapes(network)
    lane_names = {lane.get('id'): edge.get('name', '') for edge in network.iterfind('edge') for lane in edge.iterfind('lane')}
    movements = {item.get('via'): {'fromLane': f"{item.get('from')}_{item.get('fromLane')}",
                                  'toLane': f"{item.get('to')}_{item.get('toLane')}"}
                 for item in network.iterfind('connection[@via]') if not item.get('from').startswith(':')}
    storage = signal_storage(network, links, lanes, lane_nodes)
    issues = inspect_obstacles(network, street, lanes, lane_nodes, movements)
    issues.extend(signal_findings)
    issues.extend(item for lane in storage.values() for item in lane)
    issues.extend(stopped_in_signal(directory, links, storage, lane_nodes,
                                    {key: lane['length'] for key, lane in lanes.items()}))
    issues.extend(issue('reversed_straight', 'alert', 'La geometría de una conexión recta retrocede respecto al sentido de marcha.',
                        junction=item['junction'], movement=item) for item in reversed_straights(network))
    for node in osm.iterfind('node'):
        attributes = tags(node)
        if attributes.get('crossing:island') == 'yes' or attributes.get('traffic_calming') == 'island':
            issues.append(issue('island_outline_unavailable', 'alert',
                                'OpenStreetMap registra una isleta en un punto. El punto por sí solo no define un contorno elevado.',
                                junction=node.get('id'), location=[float(node.get(axis)) for axis in ('lon', 'lat')]))
    geo_file = directory / 'map.nod.xml'
    if geo_file.is_file():
        positions = {node.get('id'): [float(node.get('x')), float(node.get('y'))]
                     for node in ET.parse(geo_file).iterfind('node')}
    else:
        positions = {}
    for item in issues:
        if 'location' not in item and item.get('junction') in positions:
            item['location'] = positions[item['junction']]
        motion = item.get('movement', {})
        item['streets'] = list(dict.fromkeys(lane_names[lane] for lane in motion.values()
                                           if isinstance(lane, str) and lane_names.get(lane)))
    return {'junctionsChecked': len(street['junctions']), 'movementsChecked': len(movements),
            'mappedSurfaces': len(street['physicalSurfaces']), 'roundabouts': len(street['roundabouts']),
            'signalControllers': signal_inventory,
            'hasTrajectories': (directory / 'trajectories.xml').is_file(),
            'summary': dict(Counter(item['code'] for item in issues)), 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', default=[], help='Carpeta de una corrida guardada')
    parser.add_argument('--region', action='store_true', help='Convertir y auditar el recorte regional completo')
    parser.add_argument('--signals-only', action='store_true', help='Limitar la auditoría a los permisos semafóricos')
    parser.add_argument('--output', type=Path, default=Path('results/road-audit.json'))
    options = parser.parse_args()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'runs': {path.name: audit(path, signals_only=options.signals_only) for path in options.run}}
    if options.region or not options.run:
        _, netconvert, env = sumo_tools()
        region = coverage()
        with TemporaryDirectory(prefix='audit-network-', dir=options.output.parent) as temp:
            directory = Path(temp).resolve()
            source = write_local_extract(region['sourceBounds'], directory / 'recorte.osm.xml')
            if source is None:
                parser.exit(1, 'No se pudo extraer la red regional.\n')
            network = build_network(directory, netconvert, env, region)
            report['region'] = {**source, **audit(directory, network, signals_only=options.signals_only)}
    write_json(options.output, report)
    print(options.output)


if __name__ == '__main__':
    main()
