"""Compile the service-node notch on a copy of the 1C.3 candidate and compare it."""

from hashlib import sha256
from math import dist
from pathlib import Path
import shutil
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shapely.geometry import Point, Polygon
from shapely.validation import explain_validity

from sumo_scenario.lane_geometry import lane_shapes, reversed_straights, unit, vector, dot
from tools import sector01_probar as proof

CANDIDATE = ROOT / 'results/etapa1c3-sector01/candidato-local/a'
PREVIOUS_SHAPES = CANDIDATE / 'geometry.nod.xml'
KEPT_NODES = ('4462688320', '1155354953', '2535807404', '1957626407')
SERVICE_NODES = {'1957626365', '2480679873'}
OPPOSITE = {'fromLane': '185203633#1_0', 'via': ':2480679873_0_0', 'toLane': '185203633#2_0',
            'junction': '2480679873'}
MARGIN = 0.10


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def protected_files():
    files = []
    baseline = proof.json.loads((ROOT / 'tests/fixtures/baseline_v001.json').read_bytes())
    historic = proof.json.loads((ROOT / 'results/baseline-v001-cert-10114794/historicos-despues.json').read_bytes())
    for name, rows in historic.items():
        directory = ROOT / baseline['references'][name]['path']
        files.extend(directory / row for row in rows)
    manifest = proof.json.loads((proof.BASE / 'manifest.json').read_bytes())
    files.extend(proof.BASE / name for name in manifest['artifacts'])
    files.extend(CANDIDATE.joinpath(name) for name in (
        'network.net.xml', 'geometry.nod.xml', 'speeds.con.xml', 'recorte.osm.xml', 'service.typ.xml'))
    files.append(ROOT / 'results/etapa1c3-sector01/candidato.py')
    files.append(ROOT / 'results/etapa1c3-sector01/probar.py')
    for name in ('sector01_reproducir.py', 'sector01_probar.py', 'sector01_candidato.py', 'sector01_cerrar.py'):
        files.append(ROOT / 'tools' / name)
    for folder in ('sumo_scenario', 'urbanflow-web', 'src'):
        files.extend(path for path in (ROOT / folder).rglob('*') if path.is_file())
    return sorted({path.resolve() for path in files})


def snapshot():
    return {str(path.relative_to(ROOT)): digest(path) for path in protected_files()}


def polygon_of(network, identifier):
    node = network.find(f"junction[@id='{identifier}']")
    return Polygon([tuple(map(float, point.split(',')[:2])) for point in node.get('shape').split()]).buffer(0)


def notch(network, margin):
    """Open the signal polygon along the service axis until 2480679873 lies outside it."""
    upstream = polygon_of(network, '1957626365')
    local = polygon_of(network, '2480679873')
    origin = tuple(float(network.find("junction[@id='1957626365']").get(axis)) for axis in ('x', 'y'))
    destination = tuple(float(network.find("junction[@id='2480679873']").get(axis)) for axis in ('x', 'y'))
    forward = unit(vector(origin, destination))
    side = (-forward[1], forward[0])

    def place(along, across):
        return origin[0] + forward[0] * along + side[0] * across, origin[1] + forward[1] * along + side[1] * across

    def project(point):
        return dot(vector(origin, point), forward), dot(vector(origin, point), side)

    hole = local.buffer(margin, resolution=8)
    projected = [project(point) for point in hole.exterior.coords]
    along_min = min(item[0] for item in projected)
    across_min = min(item[1] for item in projected)
    across_max = max(item[1] for item in projected)
    along_far = max(project(point)[0] for point in upstream.exterior.coords) + 2
    sweep = Polygon([place(along_min, across_min), place(along_far, across_min),
                     place(along_far, across_max), place(along_min, across_max)])
    cut = upstream.difference(sweep)
    if cut.geom_type != 'Polygon' or not cut.is_valid or cut.interiors or cut.intersection(local).area > 0:
        raise ValueError(f'La muesca no es un polígono simple separado: {explain_validity(cut)}')
    if cut.distance(local) < margin - .001:
        raise ValueError(f'La separación quedó en {cut.distance(local):.3f} m.')
    points = []
    for point in list(cut.exterior.coords)[:-1]:
        if not points or dist(points[-1], point) > .001:
            points.append(point)
    return points, {'margin': margin, 'points': len(points), 'area': cut.area,
                    'removedArea': upstream.area - cut.area, 'separation': cut.distance(local),
                    'valid': True, 'holes': 0}


def geographic_shape(points, projection):
    origin = projection['origin']
    converted = []
    for point in points:
        lng, lat = [value + (point[0] - origin[0]) * east + (point[1] - origin[1]) * north
                    for value, east, north in zip(projection['location'], projection['east'], projection['north'])]
        converted.append(f'{lng:.9f},{lat:.9f}')
    return ' '.join(converted)


def write_nodes(directory, projection, points):
    previous = ET.parse(PREVIOUS_SHAPES)
    shapes = {node.get('id'): node.get('shape') for node in previous.findall('node')}
    if tuple(shapes) != KEPT_NODES:
        raise ValueError('La candidata 1C.3 no contiene las cuatro formas esperadas.')
    nodes = ET.Element('nodes')
    for identifier in KEPT_NODES:
        ET.SubElement(nodes, 'node', id=identifier, shape=shapes[identifier])
    ET.SubElement(nodes, 'node', id='1957626365', shape=geographic_shape(points, projection))
    ET.indent(nodes)
    ET.ElementTree(nodes).write(directory / 'geometry.nod.xml', encoding='utf-8', xml_declaration=True)
    return shapes


def compile_once(directory, points, projection):
    directory.mkdir(parents=True)
    for name in ('recorte.osm.xml', 'service.typ.xml'):
        shutil.copyfile(proof.SOURCE / name, directory / name)
    kept = write_nodes(directory, projection, points)
    command = proof.json.loads((proof.SOURCE / 'netconvert-command.json').read_bytes())['argv'][1:]
    proof.tool(directory, 'netconvert', command + ['--node-files', 'geometry.nod.xml'], 'netconvert-clip')
    raw = directory / 'network.net.xml'
    raw.rename(directory / 'clip.net.xml')
    reference = ET.parse(CANDIDATE / 'network.net.xml')
    clipped = ET.parse(directory / 'clip.net.xml')
    by_via = {link.get('via'): link for link in reference.findall('connection[@via]')}
    speeds = ET.Element('connections')
    restored = []
    blocked = []
    for row in proof.lanes_diff(reference, clipped):
        if row['before']['speed'] == row['after']['speed']:
            continue
        source = by_via.get(row['lane'])
        if source is None:
            blocked.append(row['lane'])
            continue
        ET.SubElement(speeds, 'connection', {key: source.get(key) for key in
                                             ('from', 'to', 'fromLane', 'toLane')}, speed=row['before']['speed'])
        restored.append({'lane': row['lane'], 'speed': row['before']['speed'], 'recalculated': row['after']['speed']})
    ET.indent(speeds)
    ET.ElementTree(speeds).write(directory / 'speeds.con.xml', encoding='utf-8', xml_declaration=True)
    proof.tool(directory, 'netconvert', ['--sumo-net-file', 'clip.net.xml', '--connection-files', 'speeds.con.xml',
                                        '--precision.geo', '7', '--output-file', 'network.net.xml',
                                        '--plain-output-prefix', 'final', '--proj.plain-geo', 'true',
                                        '--plain-output.lanes', 'true'], 'netconvert-final')
    return ET.parse(directory / 'network.net.xml'), {'keptShapes': kept, 'restoredSpeeds': restored,
                                                     'unrestoredLanes': blocked}


def compile_pair(out, points, projection):
    compiled = {}
    notes = {}
    for label in ('a', 'b'):
        compiled[label], notes[label] = compile_once(out / label, points, projection)
    same = proof.xml_signature(compiled['a'].getroot()) == proof.xml_signature(compiled['b'].getroot())
    return compiled, {'reproducible': same, 'runs': notes,
                      'networkSha256': {label: proof.sha(out / label / 'network.net.xml') for label in ('a', 'b')}}


def measurement(network, row, original_lanes):
    return proof.link_measurements(network, [row], original_lanes)[0]


def overlaps(network, identifier):
    subject = polygon_of(network, identifier)
    rows = []
    for node in network.findall('junction'):
        if node.get('id') == identifier or not node.get('shape') or len(node.get('shape').split()) < 3:
            continue
        try:
            other = Polygon([tuple(map(float, point.split(',')[:2])) for point in node.get('shape').split()]).buffer(0)
        except ValueError:
            continue
        if not other.is_valid or other.is_empty:
            continue
        area = subject.intersection(other).area
        if area > .001:
            rows.append({'id': node.get('id'), 'area': area})
    return rows


def gate(candidate, compiled, original):
    rules = proof.control_rules(candidate, compiled)
    rules['tlLogic'] = rules['tlLogic'] and proof.xml_signature(candidate.find('tlLogic')) == proof.xml_signature(
        compiled.find('tlLogic'))
    lanes = proof.lanes_diff(candidate, compiled)
    rules['effectiveSpeeds'] = all(row['before']['speed'] == row['after']['speed'] for row in lanes)
    connection_keys = ('from', 'to', 'fromLane', 'toLane', 'via', 'dir', 'state', 'tl', 'linkIndex')
    rules['sameConnections'] = (
        [tuple(link.get(key) for key in connection_keys) for link in candidate.findall('connection')] ==
        [tuple(link.get(key) for key in connection_keys) for link in compiled.findall('connection')])
    frozen = {row['lane'] for row in proof.lanes_diff(original, candidate)}
    after = {lane.get('id'): lane.attrib for lane in compiled.findall('edge/lane')}
    before = {lane.get('id'): lane.attrib for lane in candidate.findall('edge/lane')}
    rules['previousCorrectionsUnchanged'] = all(before[lane] == after.get(lane) for lane in frozen)
    changed_frozen = [lane for lane in sorted(frozen) if before[lane] != after.get(lane)]
    service_edges = {edge.get('id') for edge in candidate.findall('edge')
                     if edge.get('from') in SERVICE_NODES or edge.get('to') in SERVICE_NODES
                     or (edge.get('id') or '').startswith(tuple(f':{node}' for node in SERVICE_NODES))}
    unexpected = [row['lane'] for row in lanes
                  if not row['lane'].startswith(tuple(f':{node}' for node in SERVICE_NODES))
                  and row['lane'].rsplit('_', 1)[0] not in service_edges]
    rules['onlyServiceGeometryChanged'] = not unexpected
    signal = polygon_of(compiled, '1957626365')
    local = polygon_of(compiled, '2480679873')
    previous_overlap = {(row['id'], round(row['area'], 3)) for row in overlaps(candidate, '1957626365')}
    new_overlap = overlaps(compiled, '1957626365')
    increased = [row for row in new_overlap if row['area'] > dict(previous_overlap).get(row['id'], 0) + .01]
    polygon = {'valid': signal.is_valid, 'reason': explain_validity(signal), 'holes': len(signal.interiors),
               'simple': signal.exterior.is_simple, 'separationFromServiceNode': signal.distance(local),
               'overlapWithServiceNode': signal.intersection(local).area, 'points': len(list(signal.exterior.coords)) - 1,
               'increasedOverlaps': increased}
    rules['polygonSeparatesServiceNode'] = (polygon['valid'] and polygon['holes'] == 0 and polygon['simple']
                                             and polygon['overlapWithServiceNode'] == 0
                                             and polygon['separationFromServiceNode'] >= MARGIN - .01
                                             and not increased)
    original_lanes = lane_shapes(original)
    references = reversed_straights(original)
    before_links = [measurement(candidate, row, original_lanes) for row in references]
    after_links = [measurement(compiled, row, original_lanes) for row in references]
    opposite_before = measurement(candidate, OPPOSITE, original_lanes)
    opposite_after = measurement(compiled, OPPOSITE, original_lanes)
    warnings = reversed_straights(compiled)
    rules['noRemainingOrNewReversal'] = (
        not warnings and all(row['reverseMeters'] <= .001 for row in after_links)
        and opposite_after['reverseMeters'] <= opposite_before['reverseMeters'] + .001)
    return {'rules': rules, 'changedFrozenLanes': changed_frozen, 'unexpectedLaneChanges': unexpected,
            'polygon': polygon, 'linksBefore': before_links, 'linksAfter': after_links,
            'oppositeBefore': opposite_before, 'oppositeAfter': opposite_after, 'warnings': warnings,
            'laneChanges': len(lanes)}


def write_probes(path):
    routes = ET.parse(ROOT / 'results/etapa1c3-sector01/dinamica/probes.rou.xml')
    root = routes.getroot()
    vehicle = ET.SubElement(root, 'vehicle', id='probe-opposite', type='inspection', depart='775',
                            departLane='0', departSpeed='0', departPos='base')
    ET.SubElement(vehicle, 'route', edges='185203633#1 185203633#2 1346593267#0')
    ET.indent(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    routes.write(path, encoding='utf-8', xml_declaration=True)
    return path


def simulate_probes(directory, routes):
    folder = directory / 'probes'
    folder.mkdir()
    shutil.copyfile(proof.SOURCE / 'signals.add.xml', folder / 'signals.add.xml')
    proof.tool(folder, 'sumo', ['--net-file', str(directory / 'network.net.xml'), '--route-files', str(routes),
                               '--end', '1100', '--step-length', '0.05', '--seed', '42', '--time-to-teleport', '-1',
                               '--collision.action', 'warn', '--collision.check-junctions', 'true',
                               '--no-step-log', 'true', '--fcd-output', 'trajectories.xml', '--precision', '4',
                               '--device.fcd.period', '0.05', '--summary-output', 'summary.xml',
                               '--tripinfo-output', 'trips.xml', '--tripinfo-output.write-unfinished', 'true',
                               '--collision-output', 'collisions.xml'], 'sumo')
    return load_simulation(folder, routes)


def load_simulation(folder, routes):
    final = ET.parse(folder / 'summary.xml').getroot()[-1].attrib
    from collections import defaultdict
    recorded = defaultdict(list)
    for step in ET.parse(folder / 'trajectories.xml').iterfind('timestep'):
        for row in step.findall('vehicle'):
            recorded[row.get('id')].append({'time': float(step.get('time')), **row.attrib})
    trips = {row.get('id'): row.attrib for row in ET.parse(folder / 'trips.xml').findall('tripinfo')}
    log = (folder / 'sumo.log').read_text(encoding='utf-8')
    result = {key: int(final[key]) for key in ('loaded', 'inserted', 'arrived', 'running', 'waiting', 'collisions', 'teleports')}
    result.update(trips=trips, warnings=[line for line in log.splitlines() if line.startswith(('Warning', 'Error'))],
                  routesSha256=proof.sha(routes))
    return result, recorded


def traffic_ok(stats, arrivals):
    return (stats['arrived'] == arrivals and stats['loaded'] == arrivals and stats['running'] == 0
            and stats['waiting'] == 0 and stats['collisions'] == 0 and stats['teleports'] == 0
            and not stats['warnings'])


def main(out):
    out.mkdir(parents=True)
    proof.json_file(out / 'integridad-antes.json', snapshot())
    original = ET.parse(proof.SOURCE / 'network.net.xml')
    candidate = ET.parse(CANDIDATE / 'network.net.xml')
    for node in SERVICE_NODES:
        before = original.find(f"junction[@id='{node}']")
        after_node = candidate.find(f"junction[@id='{node}']")
        if any(before.get(axis) != after_node.get(axis) for axis in ('x', 'y')):
            raise ValueError(f'La candidata movió el nodo {node}.')
    projection = proof.geographic_transform(candidate, proof.SOURCE / 'map.nod.xml')
    points, designed = notch(candidate, MARGIN)
    proof.json_file(out / 'muesca.json', designed)
    compiled, build = compile_pair(out, points, projection)
    compared = gate(candidate, compiled['a'], original)
    compared['build'] = build
    required = ('tlLogic', 'roundabout', 'location', 'junctionsAndRequests', 'effectiveSpeeds', 'sameConnections',
                'previousCorrectionsUnchanged', 'onlyServiceGeometryChanged', 'polygonSeparatesServiceNode',
                'noRemainingOrNewReversal')
    accepted = build['reproducible'] and all(compared['rules'][key] for key in required)
    if accepted:
        routes = write_probes(out / 'probes.rou.xml')
        references = reversed_straights(original)
        for label, network in compiled.items():
            demand, _ = proof.simulate(out / label, network)
            probes, samples = simulate_probes(out / label, routes)
            coverage = proof.sample_probes(samples, compared['linksAfter'])
            opposite = proof.sample_probes(samples, [compared['oppositeAfter']])
            # sample_probes addresses probe-0; the opposite vehicle uses its own id.
            opposite_samples = samples['probe-opposite']
            matching = [i for i, sample in enumerate(opposite_samples) if sample['lane'] == OPPOSITE['via']]
            heading = compared['oppositeAfter']['referenceHeading']
            signed = []
            for index in sorted({i for row in matching for i in (row - 1, row) if 0 <= i < len(opposite_samples) - 1}):
                first, second = (tuple(float(opposite_samples[item][axis]) for axis in ('x', 'y'))
                                 for item in (index, index + 1))
                signed.append(dot(vector(first, second), heading))
            compared.setdefault('traffic', {})[label] = {
                'demand': {key: demand[key] for key in ('loaded', 'inserted', 'arrived', 'running', 'waiting', 'collisions', 'teleports')},
                'demandWarnings': demand['warnings'],
                'probes': {key: probes[key] for key in ('loaded', 'inserted', 'arrived', 'running', 'waiting', 'collisions', 'teleports')},
                'probeWarnings': probes['warnings'],
                'probeCoverage': [{key: row[key] for key in ('vehicle', 'lane', 'sampleCount', 'minSignedStepMeters')}
                                  for row in coverage],
                'oppositeSamples': len(matching), 'oppositeMinSignedStepMeters': min(signed, default=None),
            }
            compared['traffic'][label]['demandOk'] = traffic_ok(demand, 36)
            compared['traffic'][label]['probesOk'] = traffic_ok(probes, 6) and all(
                row['sampleCount'] > 0 and (row['minSignedStepMeters'] or -1) > 0 for row in coverage) and (
                bool(signed) and min(signed) > 0)
        for name in ('trajectories.xml', 'trips.xml', 'collisions.xml'):
            for folder in ('same-demand', 'probes'):
                left, right = (ET.parse(out / label / folder / name) for label in ('a', 'b'))
                if proof.xml_signature(left.getroot()) != proof.xml_signature(right.getroot()):
                    accepted = False
                    compared.setdefault('trafficMismatch', []).append(f'{folder}/{name}')
        accepted = accepted and all(item['demandOk'] and item['probesOk'] for item in compared['traffic'].values())
    compared['accepted'] = accepted
    proof.json_file(out / 'comparacion.json', compared)
    after = snapshot()
    proof.json_file(out / 'integridad-despues.json', after)
    before = proof.json.loads((out / 'integridad-antes.json').read_bytes())
    if before != after:
        raise ValueError('Cambió la huella de un archivo protegido.')
    if not accepted:
        raise SystemExit(2)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'results/etapa1c3b-sector01/candidato')
