"""Build a conservative clip candidate from two overlapping junction shapes."""

from collections import Counter
from pathlib import Path
import shutil
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shapely.geometry import Polygon
from tools import sector01_probar as proof


def clip_patch(network, directory):
    projection = proof.geographic_transform(network, proof.SOURCE / 'map.nod.xml')
    lanes = proof.lane_shapes(network)
    edges = {edge.get('id'): edge for edge in network.findall('edge')}
    nodes = {node.get('id'): node for node in network.findall('junction')}
    patch = ET.Element('nodes')
    used = set()
    for row in proof.reversed_straights(network):
        outgoing = lanes[row['toLane']]
        if outgoing['length'] > .21:
            continue
        pair = row['junction'], edges[outgoing['edge']].get('to')
        if pair[0] in used or pair[1] in used:
            continue
        left, right = (nodes[identifier] for identifier in pair)
        a, b = [tuple(float(node.get(axis)) for axis in ('x', 'y')) for node in (left, right)]
        east, north = proof.unit(proof.vector(a, b))
        if not (east or north):
            continue
        midpoint = tuple((x + y) / 2 for x, y in zip(a, b))
        shapes = []
        for node, side in ((left, -1), (right, 1)):
            original = Polygon([tuple(map(float, point.split(','))) for point in node.get('shape').split()])
            half_plane = Polygon([(midpoint[0] + side * along * east - across * north,
                                   midpoint[1] + side * along * north + across * east)
                                  for along, across in ((.1, -40), (.1, 40), (40, 40), (40, -40))])
            clipped = original.buffer(0).intersection(half_plane)
            if clipped.geom_type != 'Polygon' or clipped.is_empty or clipped.interiors:
                break
            points = []
            for x, y in list(clipped.exterior.coords)[:-1]:
                ox, oy = projection['origin']
                xy = [o + (x - ox) * u + (y - oy) * v for o, u, v in
                      zip(projection['location'], projection['east'], projection['north'])]
                points.append(f'{xy[0]:.9f},{xy[1]:.9f}')
            shapes.append((node.get('id'), ' '.join(points)))
        if len(shapes) == 2:
            for identifier, shape in shapes:
                ET.SubElement(patch, 'node', id=identifier, shape=shape)
            used.update(pair)
    ET.indent(patch)
    ET.ElementTree(patch).write(directory / 'geometry.nod.xml', encoding='utf-8', xml_declaration=True)


def compile_candidate(directory, original):
    directory.mkdir()
    for name in ('recorte.osm.xml', 'service.typ.xml'):
        shutil.copyfile(proof.SOURCE / name, directory / name)
    clip_patch(original, directory)
    command = proof.json.loads((proof.SOURCE / 'netconvert-command.json').read_bytes())['argv'][1:]
    proof.tool(directory, 'netconvert', command + ['--node-files', 'geometry.nod.xml'], 'netconvert-clip')
    raw = directory / 'network.net.xml'
    raw.rename(directory / 'clip.net.xml')
    clipped = ET.parse(directory / 'clip.net.xml')
    by_via = {connection.get('via'): connection for connection in original.findall('connection[@via]')}
    speeds = ET.Element('connections')
    for row in proof.lanes_diff(original, clipped):
        if row['before']['speed'] != row['after']['speed']:
            source = by_via[row['lane']]
            ET.SubElement(speeds, 'connection', {key: source.get(key) for key in
                                                ('from', 'to', 'fromLane', 'toLane')}, speed=row['before']['speed'])
    ET.indent(speeds)
    ET.ElementTree(speeds).write(directory / 'speeds.con.xml', encoding='utf-8', xml_declaration=True)
    proof.tool(directory, 'netconvert', ['--sumo-net-file', 'clip.net.xml', '--connection-files', 'speeds.con.xml',
                                        '--precision.geo', '7', '--output-file', 'network.net.xml',
                                        '--plain-output-prefix', 'final', '--proj.plain-geo', 'true',
                                        '--plain-output.lanes', 'true'], 'netconvert-final')
    return ET.parse(raw)


def gate(before, after):
    rules = proof.control_rules(before, after)
    lanes = proof.lanes_diff(before, after)
    rules['effectiveSpeeds'] = all(row['before']['speed'] == row['after']['speed'] for row in lanes)
    rules['sameConnectionsExceptExplicitEquivalentSpeed'] = (
        [proof.xml_signature(c, {'speed'}) for c in before.findall('connection')] ==
        [proof.xml_signature(c, {'speed'}) for c in after.findall('connection')])
    rules['sameProjectionAndOffset'] = all(before.find('location').get(key) == after.find('location').get(key)
                                          for key in ('netOffset', 'projParameter', 'convBoundary'))
    assert all(value for key, value in rules.items() if key not in ('connection', 'location')), rules
    return rules, lanes


def main(out, controls):
    out.mkdir()
    baseline = ET.parse(proof.SOURCE / 'network.net.xml')
    original_warnings = proof.reversed_straights(baseline)
    references = proof.link_measurements(baseline, original_warnings, proof.lane_shapes(baseline))
    candidates = [compile_candidate(out / label, baseline) for label in ('a', 'b')]
    assert proof.xml_signature(candidates[0].getroot()) == proof.xml_signature(candidates[1].getroot())
    result = {}
    for directory, candidate in zip((out / 'a', out / 'b'), candidates):
        rules, changed = gate(baseline, candidate)
        measurements = proof.link_measurements(candidate, original_warnings, proof.lane_shapes(baseline))
        original = {r['via']: r['reverseMeters'] for r in references}
        remaining = proof.reversed_straights(candidate)
        assert all(r['via'] in original and r['backwardsMeters'] <= round(original[r['via']], 2) for r in remaining)
        assert all(max(r['gapsMeters']) <= .03 for r in measurements)
        demand, fcd = proof.simulate(directory, candidate)
        probes, samples = proof.simulate(directory, candidate, controls)
        coverage = proof.sample_probes(samples, measurements)
        for stats, expected in ((demand, 36), (probes, len(references))):
            assert stats['arrived'] == expected and stats['collisions'] == stats['teleports'] == 0 and not stats['warnings']
        for static, dynamic in zip(measurements, coverage):
            assert dynamic['sampleCount'] > 0
            if static['reverseMeters'] < .001:
                assert dynamic['minSignedStepMeters'] > 0
        result[directory.name] = {'rules': rules, 'lanesChanged': changed, 'measurements': measurements,
                                  'remaining': remaining, 'demand': demand, 'probes': probes, 'coverage': coverage,
                                  'networkSha256': proof.sha(directory / 'network.net.xml'),
                                  'fcdSamples': sum(map(len, fcd.values()))}
    for subfolder in ('same-demand', 'probes'):
        for name in ('trajectories.xml', 'trips.xml', 'collisions.xml'):
            a, b = [ET.parse(out / label / subfolder / name) for label in ('a', 'b')]
            assert proof.xml_signature(a.getroot()) == proof.xml_signature(b.getroot()), name
    proof.json_file(out / 'comparacion.json', result)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
