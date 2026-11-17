"""Reproduce the local junction-shape experiment and compare the stored demand and probes."""

from collections import defaultdict
from hashlib import file_digest
import json
from math import dist
import os
from pathlib import Path
import shutil
import subprocess
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sumo_scenario.lane_geometry import dot, geographic_transform, lane_shapes, reversed_straights, unit, vector

BASE = ROOT / 'results/etapa1c-sector01-validacion'
MANIFEST = json.loads((BASE / 'manifest.json').read_bytes())
SOURCE = BASE / MANIFEST['replayId']


def sha(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def project_relative(path):
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def recorded_file(recorded):
    """Resolve a historical manifest path, absolute or relative to the project root."""
    text = str(recorded).replace('\\', '/')
    direct = Path(text)
    if direct.is_file():
        return direct
    parts = [part for part in text.split('/') if part and not part.endswith(':')]
    for index in range(len(parts)):
        relocated = ROOT.joinpath(*parts[index:])
        if relocated.is_file():
            return relocated
    raise FileNotFoundError(recorded)


def json_file(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def tool(directory, name, arguments, log):
    descriptor = MANIFEST['tools'][name]
    binary = recorded_file(descriptor['path'])
    assert sha(binary) == descriptor['sha256']
    command = [str(binary), *arguments]
    json_file(directory / (log + '-command.json'), {
        'cwd': project_relative(directory), 'argv': [project_relative(binary), *arguments],
    })
    with (directory / (log + '.log')).open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT,
                                env={**os.environ, 'SUMO_HOME': str(binary.parent.parent)})
    result.check_returncode()


def xml_signature(element, omit=()):
    return (element.tag, {key: value for key, value in element.attrib.items() if key not in omit},
            [xml_signature(child, omit) for child in element])


def make_patch(original, directory, scale):
    lanes = lane_shapes(original)
    projection = geographic_transform(original, SOURCE / 'map.nod.xml')
    nodes = {node.get('id'): node for node in original.findall('junction')}
    edges = {edge.get('id'): edge for edge in original.findall('edge')}
    output = ET.Element('nodes')
    chosen = {}
    for row in reversed_straights(original):
        before, after = (lanes[row[key]] for key in ('fromLane', 'toLane'))
        if after['length'] > .21:
            continue
        for identifier, leg in ((row['junction'], before['points'][-2:]),
                                (edges[after['edge']].get('to'), after['points'][:2])):
            chosen.setdefault(identifier, unit(vector(*leg)))
    for identifier, forward in sorted(chosen.items()):
        x, y = (float(nodes[identifier].get(axis)) for axis in ('x', 'y'))
        east, north = forward
        points = [(x + a * east - b * north, y + a * north + b * east)
                  for a, b in [(-scale, -4), (-scale, 4), (scale, 4), (scale, -4)]]
        shape = []
        for px, py in points:
            x0, y0 = projection['origin']
            coordinates = [o + (px - x0) * u + (py - y0) * v for o, u, v in
                           zip(projection['location'], projection['east'], projection['north'])]
            shape.append(f'{coordinates[0]:.9f},{coordinates[1]:.9f}')
        ET.SubElement(output, 'node', id=identifier, shape=' '.join(shape))
    ET.indent(output)
    ET.ElementTree(output).write(directory / 'geometry.nod.xml', encoding='utf-8', xml_declaration=True)


def build(directory, original, scale):
    directory.mkdir()
    for name in ('recorte.osm.xml', 'service.typ.xml'):
        shutil.copyfile(SOURCE / name, directory / name)
    command = json.loads((SOURCE / 'netconvert-command.json').read_bytes())['argv'][1:]
    if scale is not None:
        make_patch(original, directory, scale)
        command += ['--node-files', 'geometry.nod.xml']
    tool(directory, 'netconvert', command, 'netconvert')
    return ET.parse(directory / 'network.net.xml')


def control_rules(left, right):
    exact = ('connection', 'tlLogic', 'roundabout', 'location')
    comparable = {tag: [xml_signature(x) for x in left.findall(tag)] ==
                  [xml_signature(x) for x in right.findall(tag)] for tag in exact}
    comparable['junctionsAndRequests'] = (
        [xml_signature(x, {'shape', 'customShape'}) for x in left.findall('junction')] ==
        [xml_signature(x, {'shape', 'customShape'}) for x in right.findall('junction')])
    comparable['edgesLanesAndPermissions'] = (
        [xml_signature(x, {'shape', 'length', 'speed'}) for x in left.findall('edge')] ==
        [xml_signature(x, {'shape', 'length', 'speed'}) for x in right.findall('edge')])
    return comparable


def lanes_diff(left, right):
    a = {lane.get('id'): lane.attrib for lane in left.findall('edge/lane')}
    b = {lane.get('id'): lane.attrib for lane in right.findall('edge/lane')}
    return [{'lane': key, 'before': a[key], 'after': b[key]} for key in a if a[key] != b[key]]


def link_measurements(network, references, original_lanes):
    lanes = lane_shapes(network)
    output = []
    for row in references:
        before, middle, after = (lanes[row[k]] for k in ('fromLane', 'via', 'toLane'))
        a = unit(vector(*original_lanes[row['fromLane']]['points'][-2:]))
        b = unit(vector(*original_lanes[row['toLane']]['points'][:2]))
        forward = unit((a[0] + b[0], a[1] + b[1]))
        measured = [dot(vector(x, y), forward) for x, y in zip(middle['points'], middle['points'][1:])]
        output.append({**row, 'referenceHeading': forward, 'signedStepsMeters': measured,
                       'sumoLength': middle['length'], 'reverseMeters': -sum(min(0, x) for x in measured),
                       'gapsMeters': [dist(before['points'][-1], middle['points'][0]),
                                      dist(middle['points'][-1], after['points'][0])]})
    return output


def demand_probes(directory, references):
    root = ET.Element('routes')
    ET.SubElement(root, 'vType', id='inspection', vClass='passenger', maxSpeed='2',
                  sigma='0', speedFactor='1', lcStrategic='0', lcSpeedGain='0', lcKeepRight='0')
    for index, row in enumerate(references):
        start, lane = row['fromLane'].rsplit('_', 1)
        end = row['toLane'].rsplit('_', 1)[0]
        # The service feeder is 0.2 m. Start on its legal predecessor.
        route = start
        if row['fromLane'] == '-185203633#2_0':
            route = '482520536#14 482520536#15 ' + start
        vehicle = ET.SubElement(root, 'vehicle', id=f'probe-{index}', type='inspection',
                                depart=str(index * 155), departLane=lane, departSpeed='0', departPos='base')
        ET.SubElement(vehicle, 'route', edges=f'{route} {end}')
    ET.indent(root)
    ET.ElementTree(root).write(directory / 'probes.rou.xml', encoding='utf-8', xml_declaration=True)


def simulate(directory, network, routes=None):
    folder = directory / ('probes' if routes else 'same-demand')
    folder.mkdir()
    if routes is None:
        for name in ('routes.rou.xml', 'signals.add.xml', 'sector01.sumocfg'):
            shutil.copyfile(SOURCE / name, folder / name)
        args = ['-c', 'sector01.sumocfg', '--net-file', str(directory / 'network.net.xml')]
    else:
        shutil.copyfile(SOURCE / 'signals.add.xml', folder / 'signals.add.xml')
        args = ['--net-file', str(directory / 'network.net.xml'), '--route-files', str(routes),
                '--end', '850', '--step-length', '0.05', '--seed', '42', '--time-to-teleport', '-1',
                '--collision.action', 'warn', '--collision.check-junctions', 'true', '--no-step-log', 'true',
                '--fcd-output', 'trajectories.xml', '--precision', '4', '--device.fcd.period', '0.05',
                '--summary-output', 'summary.xml', '--tripinfo-output', 'trips.xml',
                '--tripinfo-output.write-unfinished', 'true', '--collision-output', 'collisions.xml']
    tool(folder, 'sumo', args, 'sumo')
    final = ET.parse(folder / 'summary.xml').getroot()[-1].attrib
    fcd = defaultdict(list)
    for step in ET.parse(folder / 'trajectories.xml').iterfind('timestep'):
        for row in step.findall('vehicle'):
            fcd[row.get('id')].append({'time': float(step.get('time')), **row.attrib})
    trips = {row.get('id'): row.attrib for row in ET.parse(folder / 'trips.xml').findall('tripinfo')}
    log = (folder / 'sumo.log').read_text(encoding='utf-8')
    result = {key: int(final[key]) for key in ('loaded', 'inserted', 'arrived', 'running', 'waiting', 'collisions', 'teleports')}
    result.update(trips=trips, warnings=[line for line in log.splitlines() if line.startswith(('Warning', 'Error'))],
                  routesSha256=sha(routes or folder / 'routes.rou.xml'))
    return result, fcd


def sample_probes(fcd, references):
    result = []
    for index, row in enumerate(references):
        samples = fcd[f'probe-{index}']
        matching = [i for i, sample in enumerate(samples) if sample['lane'] == row['via']]
        positions = [samples[i] for i in matching]
        pairs = sorted({i for j in matching for i in (j - 1, j) if 0 <= i < len(samples) - 1})
        forward = row['referenceHeading']
        signed = []
        for i in pairs:
            a, b = (tuple(float(samples[j][k]) for k in ('x', 'y')) for j in (i, i+1))
            signed.append(dot(vector(a, b), forward))
        result.append({'vehicle': f'probe-{index}', 'lane': row['via'], 'sampleCount': len(positions),
                       'minSignedStepMeters': min(signed, default=None), 'internalSamples': positions,
                       'entryAndExitSamples': [samples[i] for i in sorted({j for k in pairs for j in (k, k+1)})]})
    return result


def main(directory):
    directory.mkdir()
    original = ET.parse(SOURCE / 'network.net.xml')
    references = reversed_straights(original)
    original_lanes = lane_shapes(original)
    report = {}
    probes = None
    for name, scale in [('control', None), ('local-a', .3), ('local-b', .3)]:
        folder = directory / name
        network = build(folder, original, scale)
        measurements = link_measurements(network, references, original_lanes)
        report[name] = {'controls': control_rules(original, network), 'lanesChanged': lanes_diff(original, network),
                        'links': measurements, 'warnings': reversed_straights(network),
                        'networkSha256': sha(folder / 'network.net.xml')}
        if name == 'local-b':
            assert xml_signature(network.getroot()) == xml_signature(candidate.getroot())
            continue
        if name == 'local-a':
            candidate = network
        else:
            assert xml_signature(network.getroot()) == xml_signature(original.getroot())
            demand_probes(directory, references)
            probes = directory / 'probes.rou.xml'
        report[name]['sameDemand'], recorded = simulate(folder, network)
        report[name]['probes'], samples = simulate(folder, network, probes)
        report[name]['probeCoverage'] = sample_probes(samples, measurements)
        report[name]['recordedFcdSamples'] = sum(map(len, recorded.values()))
        json_file(directory / 'comparacion.json', report)
    json_file(directory / 'comparacion.json', report)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
