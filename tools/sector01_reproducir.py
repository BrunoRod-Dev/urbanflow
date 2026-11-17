"""Run the Williman sector experiment in a new directory under results."""

from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from sumo_scenario.regional_map import SNAPSHOT, regional_network, write_local_extract
from sumo_scenario.regional_inventory import direction, tags
from sumo_scenario.geo_projection import to_geographic
from sumo_scenario.lane_geometry import replay_geometry, reversed_straights
from sumo_scenario.study import (
    VEHICLE_LENGTHS, VEHICLE_TYPES, fcd_frames, map_network, permits, prepare_signal_recording,
    save_study, signal_replay, write_json,
)
from test_baseline_v001 import BASELINE, network_signature

SOURCE = [-54.945, -34.9618, -54.9358, -34.9429]
POLYGON = [(-54.94415, -34.9608), (-54.9364, -34.9608), (-54.9364, -34.9488),
           (-54.937, -34.9488), (-54.937, -34.9437), (-54.94415, -34.9437)]
HOME = ROOT / 'results/baseline-v001-tools/portable/sumo-1.26.0'
HASHES = {
    'sumo': 'dcdbf4fe1f8268816cda2d0631d407fd8e63b0cad5f3e57fe9cf235d9dece926',
    'netconvert': '4174c17db813d413c85cdf7ad99a5f59b537ddf80f8caac9e1dfe87a35cb6b51',
}
STUDY = '01c20261113000000000000000000001'
REPLAY_BOUNDS = [min(x for x, y in POLYGON), min(y for x, y in POLYGON),
                 max(x for x, y in POLYGON), max(y for x, y in POLYGON)]
CHECK_NODES = {
    'Península': '840834919', 'Emilio Sader': '1918169993', 'Miami hacia Mansa': '1918169990',
    'Miami hacia Península': '1761803419', 'El Pinar': '1761803556', 'Pirineos': '1761803640',
    'Acceso de servicio': '1957626365', 'Paralela al sur': '1761803535',
}


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def project_relative(path):
    """Record a project path without embedding this machine's absolute prefix."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def osm_id(edge):
    return edge.lstrip('-').split('#')[0]


def command(directory, binary, arguments):
    executable = HOME / 'bin' / f'{binary}.exe'
    argv = [str(executable), *arguments]
    write_json(directory / f'{binary}-command.json', {
        'cwd': project_relative(directory), 'SUMO_HOME': project_relative(HOME),
        'argv': [project_relative(executable), *arguments],
    })
    result = subprocess.run(argv, cwd=directory, env={**os.environ, 'SUMO_HOME': str(HOME)},
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    (directory / f'{binary}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    result.check_returncode()
    return result.stdout + result.stderr


def compile_network(directory):
    directory.mkdir()
    region = write_local_extract(SOURCE, directory / 'recorte.osm.xml')
    assert region and region['snapshot'] == BASELINE['snapshot']
    # Keep mapped local service roads for passenger probes. The default permits delivery,
    # pedestrians and bicycles only. OSM tags still apply during import.
    (directory / 'service.typ.xml').write_text(
        '<types><type id="highway.service" numLanes="1" speed="5.56" priority="1" oneway="false" '
        'allow="delivery pedestrian bicycle passenger"/></types>\n', encoding='utf-8')
    types = HOME / 'data/typemap/osmNetconvert.typ.xml'
    return command(directory, 'netconvert', [
        '--osm-files', 'recorte.osm.xml', '--keep-edges.in-geo-boundary',
        ','.join(str(c) for point in POLYGON for c in point), '--keep-edges.by-vclass', 'passenger,bus',
        '--type-files', f'{types},service.typ.xml', '--osm.turn-lanes', 'true', '--geometry.remove', 'true',
        '--tls.guess-signals', 'true', '--tls.join', 'true', '--tls.join-dist', '30',
        '--tls.default-type', 'actuated', '--no-turnarounds', 'true', '--roundabouts.guess', 'true',
        '--output.street-names', 'true', '--output.original-names', 'true', '--output-file', 'network.net.xml',
        '--plain-output-prefix', 'map', '--proj.plain-geo', 'true', '--plain-output.lanes', 'true',
        '--precision.geo', '7', '--aggregate-warnings', '-1',
    ])


def network_parts(network):
    edges = {edge.get('id'): edge for edge in network.findall('edge[@from]')}
    links = defaultdict(set)
    for connection in network.findall('connection'):
        a, b = connection.get('from'), connection.get('to')
        if a in edges and b in edges:
            links[a, b].add((int(connection.get('fromLane')), int(connection.get('toLane'))))
    return edges, links


def make_demand(edges, links, destination):
    def chain(start, stop, ways):
        by_start = defaultdict(list)
        for key, edge in edges.items():
            if key.split('#')[0] in ways:
                by_start[edge.get('from')].append(key)
        result, visited = [], set()
        while start != stop:
            assert start not in visited and len(by_start[start]) == 1, (start, stop, by_start[start])
            visited.add(start)
            edge, = by_start[start]
            result.append(edge)
            start = edges[edge].get('to')
        return result

    north = chain('840834919', '12455572997', {'99944425', '482520536', '1346593267'})
    south = chain('2351793223', '840834968', {'164559876', '99944449'})
    peninsula = chain('840834656', '840834919', {'70521183'})
    miami = chain('1612432454', '1918169990', {'-100522115'})
    pinar = chain('1156825024', '1761803556', {'102681399'})
    pirineos = chain('1612432350', '1761803640', {'148146704'})
    side_exit = chain('1761803640', '1612432350', {'-148146704'})
    sader = chain('1918169993', '1159037702', {'181384679'})

    def through(path, node):
        return path[:next(i + 1 for i, key in enumerate(path) if edges[key].get('to') == node)]

    def after(path, node):
        return path[next(i for i, key in enumerate(path) if edges[key].get('from') == node):]

    probes = [
        ('mansa', peninsula + north, 1),
        ('peninsula-carril-0', south, 0),
        ('peninsula-carril-1', through(south, '1761803363'), 1),
        ('salida-sader', peninsula + through(north, '1918169993') + sader, 1),
        ('entrada-miami', miami + after(north, '1918169990'), 0),
        ('salida-miami', peninsula + through(north, '1918169990') + ['100522115#1', '100522115#2'], 1),
        ('miami-entre-calzadas', miami + ['-100522115#0']
         + through(after(south, '1761803419'), '1761803363'), 0),
        ('entrada-pinar', pinar + after(north, '1761803556'), 0),
        ('entrada-pirineos', pirineos + after(north, '1761803640'), 0),
        ('salida-pirineos', peninsula + through(north, '1761803640') + side_exit, 1),
        ('entrada-servicio', ['185203633#1', '185203633#2'] + after(north, '1957626365'), 0),
        ('salida-servicio', peninsula + through(north, '1957626365') + ['-185203633#2', '-185203633#1'], 1),
    ]
    demand = ET.Element('routes')
    ET.SubElement(demand, 'vType', id='car', **{key: str(val) for key, val in VEHICLE_TYPES['car'].items()},
                  sigma='0', speedFactor='1')
    for name, path, depart_lane in probes:
        lanes = {depart_lane}
        for a, b in zip(path, path[1:]):
            lanes = {j for i, j in links[a, b] if i in lanes and permits(edges[b].findall('lane')[j], 'passenger')}
            assert lanes, (name, a, b, 'no continuous passenger lane chain')
        ET.SubElement(demand, 'route', id=name, edges=' '.join(path))
    planned = {}
    for repetition in range(3):
        for i, (name, _, depart_lane) in enumerate(probes):
            vehicle = f'{name}-{repetition + 1}'
            planned[vehicle] = 10 + repetition * 100 + 7 * i
            ET.SubElement(demand, 'vehicle', id=vehicle, type='car', route=name, depart=str(planned[vehicle]),
                          departLane=str(depart_lane), departSpeed='0')
    ET.indent(demand)
    ET.ElementTree(demand).write(destination, encoding='utf-8', xml_declaration=True)
    return probes, planned


def run_simulation(directory, network, demand):
    probes, planned = demand
    signals = prepare_signal_recording(network, directory)
    assert signals
    config = ET.Element('configuration')
    sections = {
        'input': {'net-file': 'network.net.xml', 'route-files': 'routes.rou.xml', 'additional-files': signals[1]},
        'time': {'begin': '0', 'end': '540', 'step-length': '0.5'},
        'processing': {'time-to-teleport': '-1', 'collision.action': 'warn', 'collision.check-junctions': 'true',
                       'ignore-route-errors': 'false'},
        'random_number': {'seed': '42'},
        'output': {'fcd-output': 'trajectories.xml', 'fcd-output.geo': 'true', 'precision.geo': '7',
                   'device.fcd.period': '0.5', 'summary-output': 'summary.xml', 'tripinfo-output': 'trips.xml',
                   'tripinfo-output.write-unfinished': 'true', 'tripinfo-output.write-undeparted': 'true',
                   'collision-output': 'collisions.xml'},
        'report': {'no-step-log': 'true'},
    }
    for name, options in sections.items():
        section = ET.SubElement(config, name)
        for key, value in options.items():
            ET.SubElement(section, key, value=value)
    ET.indent(config)
    ET.ElementTree(config).write(directory / 'sector01.sumocfg', encoding='utf-8', xml_declaration=True)
    log = command(directory, 'sumo', ['-c', 'sector01.sumocfg'])
    summary = ET.parse(directory / 'summary.xml').getroot()[-1].attrib
    trips = {row.get('id'): row.attrib for row in ET.parse(directory / 'trips.xml').findall('tripinfo')}
    collisions = len(ET.parse(directory / 'collisions.xml').findall('collision'))
    paths = {name: path for name, path, _ in probes}
    lanes = defaultdict(list)
    stop_runs = defaultdict(int)
    longest = Counter()
    fcd = ET.parse(directory / 'trajectories.xml')
    valid_lanes = {lane.get('id') for lane in network.findall('edge/lane')}
    bad_samples = []
    for vehicle in fcd.iterfind('timestep/vehicle'):
        identifier = vehicle.get('id')
        lane = vehicle.get('lane')
        if not lane.startswith(':'):
            edge = lane.rsplit('_', 1)[0]
            if not lanes[identifier] or edge != lanes[identifier][-1]:
                lanes[identifier].append(edge)
        stop_runs[identifier] = stop_runs[identifier] + 1 if float(vehicle.get('speed')) < .1 else 0
        longest[identifier] = max(longest[identifier], stop_runs[identifier])
        if lane not in valid_lanes:
            bad_samples.append([identifier, lane])
    route_results = {}
    for identifier, trip in trips.items():
        name = identifier.rsplit('-', 1)[0]
        observed = lanes[identifier]
        planned_path = paths[name]
        # At 0.5 s very short edges can pass between samples. SUMO verifies the full route.
        route_order = iter(planned_path)
        ordered = all(edge in route_order for edge in observed)
        route_results[identifier] = {'observedEdges': observed, 'ordered': ordered,
                                     'endpointsConfirmed': bool(observed) and observed[0] == planned_path[0]
                                     and trip['departLane'].rsplit('_', 1)[0] == planned_path[0]
                                     and trip['arrivalLane'].rsplit('_', 1)[0] == planned_path[-1],
                                     'arrival': float(trip['arrival']), 'duration': float(trip['duration']),
                                     'departLane': trip['departLane'], 'arriveLane': trip['arrivalLane'],
                                     'departDelay': float(trip['departDelay']),
                                     'longestStoppedSeconds': longest[identifier] / 2,
                                     'waitingTime': float(trip['waitingTime'])}
    result = {'summary': summary, 'trips': route_results, 'collisions': collisions,
              'unknownLaneSamples': bad_samples, 'warnings': [line for line in log.splitlines()
                                                             if line.startswith(('Warning:', 'Error:'))],
              'trajectorySamples': sum(1 for _ in fcd.iterfind('timestep/vehicle'))}
    write_json(directory / 'simulation-result.json', result)
    assert int(summary['inserted']) == int(summary['arrived']) == len(planned)
    assert set(trips) == set(planned) and all(t['arrival'] >= 0 for t in route_results.values())
    assert all(t['ordered'] and t['endpointsConfirmed'] for t in route_results.values())
    assert not bad_samples and not collisions and int(summary['collisions']) == 0 and int(summary['teleports']) == 0
    assert not re.search(r'teleport|no valid route|has no connection|collision|jammed', log, flags=re.I)
    return result


def audit_network(directory, network, edges, links):
    _, osm_nodes, points, osm_ways, _ = regional_network()
    osm = ET.parse(directory / 'recorte.osm.xml')
    osm_road_tags = {way.get('id'): tags(way) for way in osm.findall('way')}
    assert all(osm_id(key) in osm_road_tags for key in edges)
    wrong_way = [key for key in edges if (key.startswith('-') and
                 direction(osm_road_tags[osm_id(key)]) in ('forward', 'inferred-forward')) or
                 (not key.startswith('-') and direction(osm_road_tags[osm_id(key)]) == 'reverse')]
    assert not wrong_way, wrong_way
    disconnected = [(a, b) for a, b in links if edges[a].get('to') != edges[b].get('from')]
    assert not disconnected, disconnected
    audit_joins = []
    for label, node in CHECK_NODES.items():
        incoming = [key for key, edge in edges.items() if edge.get('to') == node]
        outgoing = [key for key, edge in edges.items() if edge.get('from') == node]
        assert incoming and outgoing, label
        for key in incoming + outgoing:
            assert node in osm_ways[osm_id(key)][1], (node, key)
        connection_rows = [{'from': a, 'to': b, 'lanePairs': sorted(links[a, b])}
                           for a in incoming for b in outgoing if (a, b) in links]
        assert connection_rows, label
        junction = network.find(f'junction[@id="{node}"]')
        audit_joins.append({'name': label, 'osmNode': node, 'point': points[node],
                            'junctionType': junction.get('type'), 'incoming': incoming, 'outgoing': outgoing,
                            'connections': connection_rows})

    log = (directory / 'netconvert.log').read_text(encoding='utf-8')
    ignored = set(re.findall(r"Ignoring restriction relation '(\d+)'", log))
    relations = []
    for relation in osm.findall('relation'):
        identifier = relation.get('id')
        members = [node.attrib for node in relation.findall('member')]
        by_role = defaultdict(list)
        for member in members:
            by_role[member['role']].append(member['ref'])
        used = {osm_id(key) for key in edges}
        via = by_role['via']
        value = tags(relation).get('restriction')
        row = {'id': identifier, 'restriction': value, 'members': members, 'importerIgnored': identifier in ignored}
        if len(via) == 1 and via[0] in osm_nodes:
            node, = via
            incoming = [key for key, edge in edges.items() if edge.get('to') == node and osm_id(key) in by_role['from']]
            outgoing = [key for key, edge in edges.items() if edge.get('from') == node and osm_id(key) in by_role['to']]
            row['incoming'], row['outgoing'] = incoming, outgoing
            if incoming and outgoing and value.startswith('no_'):
                assert not any((a, b) in links for a in incoming for b in outgoing), identifier
                row['status'] = 'prohibited-connection-absent'
            else:
                assert not incoming or not outgoing, identifier
                row['status'] = 'outside-or-boundary-member-absent'
        else:
            assert any(ref not in used for ref in by_role['from'] + by_role['to']), identifier
            row['status'] = 'outside-or-boundary-member-absent'
        relations.append(row)
    local_rule = next(row for row in relations if row['id'] == '7104488')
    assert local_rule['status'] == 'prohibited-connection-absent' and not local_rule['importerIgnored']

    rings = []
    for ring in network.findall('roundabout'):
        keys = ring.get('edges').split()
        forward = {edges[key].get('from'): edges[key].get('to') for key in keys}
        visited = set()
        node = start = next(iter(forward))
        while node in forward and node not in visited:
            visited.add(node)
            node = forward[node]
        assert node == start and len(keys) == len(visited)
        for a in keys:
            next_edge, = [b for b in keys if edges[b].get('from') == edges[a].get('to')]
            assert (a, next_edge) in links, (a, next_edge)
        ways = sorted({osm_id(key) for key in keys})
        rings.append({'edges': keys, 'osmWays': ways, 'connectedDirectedRing': True,
                      'includesExplicitRoundabout': any(osm_road_tags[way].get('junction') == 'roundabout'
                                                        for way in ways)})

    # A geometry simplification may join consecutive ways. Preserve and report its
    # source IDs so connections can be traced to OSM junctions after the merge.
    unresolved = []
    for a, b in links:
        node = edges[a].get('to')
        supports = []
        for key in (a, b):
            edge = edges[key]
            provenance = {osm_id(key)}
            for param in edge.iter('param'):
                if param.get('key') == 'origId':
                    provenance.update(osm_id(ref) for ref in param.get('value').split())
            supports.append(any(node in osm_ways[way][1] for way in provenance if way in osm_ways))
        if not all(supports):
            unresolved.append([a, node, b])

    rim = []
    for node in network.findall('junction'):
        node_id = node.get('id')
        if node_id.startswith(':'):
            continue
        incoming = [key for key, edge in edges.items() if edge.get('to') == node_id]
        outgoing = [key for key, edge in edges.items() if edge.get('from') == node_id]
        if not incoming or not outgoing:
            rim.append({'node': node_id, 'incoming': incoming, 'outgoing': outgoing})
    assert not set(CHECK_NODES.values()) & {row['node'] for row in rim}
    return {'edges': len(edges), 'lanes': sum(len(edge.findall('lane')) for edge in edges.values()),
            'junctions': sum(not node.get('id').startswith(':') for node in network.findall('junction')),
            'externalLaneConnections': sum(map(len, links.values())), 'rings': rings,
            'junctionInventory': audit_joins, 'restrictions': relations, 'terminals': rim,
            'controls': [{'id': item.get('id'), 'type': item.get('type'), 'provenance': 'SUMO inferred',
                          'phases': [phase.attrib for phase in item.findall('phase')]}
                         for item in network.findall('tlLogic')],
            'tagsMissingByImportedWay': {attribute: sum(not any(osm_road_tags[way].get(key) for key in alternatives)
                                                      for way in {osm_id(edge) for edge in edges})
                                        for attribute, alternatives in {
                                            'lanes': ('lanes', 'lanes:forward', 'lanes:backward'),
                                            'maxspeed': ('maxspeed', 'maxspeed:forward', 'maxspeed:backward'),
                                            'turn:lanes': ('turn:lanes', 'turn:lanes:forward', 'turn:lanes:backward'),
                                        }.items()},
            'unresolvedConnectionProvenance': unresolved, 'reverseShapes': reversed_straights(network),
            'warnings': [line for line in log.splitlines() if line.startswith('Warning:')]}


def make_replay(directory, out, network, probes, result):
    used = {edge for _, path, _ in probes for edge in path}
    approaches = {path[0]: label for label, path, _ in probes}
    motion = replay_geometry(network, directory / 'map.nod.xml')
    if not motion.get('projection'):
        raise AssertionError(motion.get('projectionError') or 'La red no tiene una proyección utilizable.')
    vehicles = []
    frames = fcd_frames(directory / 'trajectories.xml', {'incoming': {key: key for key in approaches}},
                        geographic=True, vehicle_lengths=VEHICLE_LENGTHS, vehicle_index=vehicles)
    assert len(vehicles) == int(result['summary']['arrived'])
    geometry = map_network(directory, used)
    signals = signal_replay(directory, network)
    assert signals and signals['states'] and signals['approaches']
    scope = regional_network()[2]
    midpoint = [(a + b) / 2 for a, b in zip(scope['840834919'], scope['1761803640'])]
    stats = {'title': 'Sector 01 · Punta del Este → Mansa', 'location': midpoint, 'bounds': REPLAY_BOUNDS,
             'clicked': midpoint, 'roundabout': False, 'seed': 42, 'seconds': 540,
             'trips': len(vehicles), 'arrived': int(result['summary']['arrived']),
             'inserted': int(result['summary']['inserted']), 'usedEdges': sorted(used),
             'traffic': {'source': 'sample', 'durationMinutes': 5, 'movements': []},
             'assumptions': ['Candidato técnico. Demanda sintética. Programas y prioridades inferidos por SUMO.',
                             'Los permisos de las vías de servicio requieren comprobación de campo.']}
    save_study(directory, stats, {'network': geometry, 'approaches': approaches, 'frames': frames,
                                'laneMotion': motion, 'vehicleTypes': VEHICLE_TYPES, 'vehicleIndex': vehicles,
                                'signalReplay': signals}, [])
    write_json(directory / 'status.json', {'stage': 'ready', 'message': 'Corrida sintética de referencia.'})
    projections = motion['projection']

    def geo(xy):
        return [round(value, 7) for value in to_geographic(xy, projections)]

    def feature(geometry_type, coordinates, **properties):
        return {'type': 'Feature', 'geometry': {'type': geometry_type, 'coordinates': coordinates},
                'properties': properties}

    layers = []
    for lane, item in motion['lanes'].items():
        if not lane.startswith(':'):
            layers.append(feature('LineString', [geo(pt) for pt in item['points']], kind='lane', lane=lane,
                                  edge=item['edge'], osmWay=osm_id(item['edge']), used=item['edge'] in used))
    for link in network.findall('connection[@via]'):
        a, b = link.get('from'), link.get('to')
        if a.startswith(':'):
            continue
        internal = motion['lanes'][link.get('via')]['points']
        layers.append(feature('LineString', [geo(pt) for pt in internal], kind='connection', origin=a, destination=b,
                              fromLane=link.get('fromLane'), toLane=link.get('toLane'), control=link.get('tl'),
                              state=link.get('state'), direction=link.get('dir'), visibility=link.get('visibility')))
    layers.extend(feature('Point', row['point'], kind='signal', controller=row['controller'],
                          groups=row['indices'], provenance='SUMO inferred') for row in signals['approaches'])
    layers.extend(feature('Point', scope[node], kind='audit-node', name=label, osmNode=node)
                  for label, node in CHECK_NODES.items())
    layers.append(feature('Polygon', [[*POLYGON, POLYGON[0]]], kind='compile-boundary'))
    write_json(out / 'sector01.geojson', {'type': 'FeatureCollection', 'features': layers})


def freeze(value):
    if isinstance(value, dict):
        return [[freeze(k), freeze(v)] for k, v in sorted(value.items())]
    if isinstance(value, (list, tuple)):
        return [freeze(item) for item in value]
    return value


def main(out):
    out.mkdir()
    assert sha(SNAPSHOT) == BASELINE['snapshotSha256']
    versions = {}
    for binary, expected in HASHES.items():
        executable = HOME / 'bin' / f'{binary}.exe'
        assert sha(executable) == expected
        version = subprocess.check_output([str(executable), '--version'], text=True)
        assert f'{binary} 1.26.0' in version
        (out / f'{binary}-version.txt').write_text(version, encoding='utf-8')
        versions[binary] = {'path': project_relative(executable), 'sha256': expected,
                            'version': version.splitlines()[:2]}
    a, b = out / STUDY, out / 'repeticion-b'
    for directory in (a, b):
        compile_network(directory)
    networks = [ET.parse(directory / 'network.net.xml') for directory in (a, b)]
    signatures = [network_signature(network) for network in networks]
    comparison = {}
    for k in signatures[0]:
        left, right = (freeze(signature[k]) for signature in signatures)
        comparison[k] = {'match': left == right, 'sha256': [
            sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            for value in (left, right)]}
        if left != right:
            write_json(out / f'diferencia-{k}.json', {'a': left, 'b': right})
    write_json(out / 'semantic-comparison.json', comparison)
    assert sha(a / 'recorte.osm.xml') == sha(b / 'recorte.osm.xml')
    assert all(row['match'] for row in comparison.values())
    assert ET.tostring(networks[0].getroot()) == ET.tostring(networks[1].getroot()), 'XML tree differs'
    edges, links = network_parts(networks[0])
    demand = make_demand(edges, links, a / 'routes.rou.xml')
    (b / 'routes.rou.xml').write_bytes((a / 'routes.rou.xml').read_bytes())
    results = [run_simulation(directory, network, demand) for directory, network in zip((a, b), networks)]
    equivalent = {}
    for name in ('trajectories.xml', 'trips.xml', 'summary.xml', 'signal-states.xml', 'collisions.xml'):
        roots = [ET.parse(directory / name).getroot() for directory in (a, b)]
        if name == 'summary.xml':
            # SUMO's processing time is wall-clock performance, not simulated time.
            for root in roots:
                for step in root.findall('step'):
                    step.attrib.pop('duration', None)
        left, right = (ET.tostring(root) for root in roots)
        equivalent[name] = {'match': left == right, 'sha256': [sha256(x).hexdigest() for x in (left, right)]}
    write_json(out / 'simulation-comparison.json', equivalent)
    assert all(row['match'] for row in equivalent.values()), equivalent
    audit = audit_network(a, networks[0], edges, links)
    write_json(out / 'network-audit.json', audit)
    make_replay(a, out, networks[0], demand[0], results[0])
    write_json(out / 'manifest.json', {
        'schemaVersion': 1, 'sector': '01-punta-mansa', 'revision': 'candidato-01',
        'validation': 'technical-candidate', 'fieldValidated': False, 'roadCorrectionFiles': [],
        'scope': CHECK_NODES, 'snapshot': {'path': project_relative(SNAPSHOT), 'date': BASELINE['snapshot'],
                                          'sha256': BASELINE['snapshotSha256']},
        'sourceBounds': SOURCE, 'compilePolygon': POLYGON, 'tools': versions,
        'defaultTypeMapSha256': sha(HOME / 'data/typemap/osmNetconvert.typ.xml'),
        'assumptions': ['Synthetic demand', 'SUMO actuated signal programs',
                        'Passenger access and default geometry for mapped service ways unless tagged otherwise'],
        'replayId': STUDY, 'artifacts': {path.relative_to(out).as_posix(): sha(path)
                                       for path in sorted(out.rglob('*')) if path.is_file()},
    })


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
