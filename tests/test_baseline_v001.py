"""Read-only baseline checks. Run with python -B -m unittest discover -s tests -p test_baseline_v001.py."""

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import gzip
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from src import study_server
from sumo_scenario.lane_geometry import reversed_straights
from sumo_scenario.study import read_network
from sumo_scenario.study_comparison import compare_studies


ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / 'tests/fixtures/baseline_v001.json').read_text(encoding='utf-8'))


def attributes(element, omit=()):
    return tuple(sorted((name, value) for name, value in element.attrib.items() if name not in omit))


def lane_pair(link):
    return tuple(f'{link.attrib[side]}_{link.attrib[side + "Lane"]}' for side in ('from', 'to'))


def network_signature(net):
    """Compare within one snapshot, retaining directed exterior edge and lane identities."""
    root = net.getroot() if isinstance(net, ET.ElementTree) else net
    if root.tag != 'net' or root.find('location') is None or root.find('edge[@from]/lane') is None:
        raise ValueError('Se requiere una red SUMO compilada con ubicación y carriles exteriores.')
    lanes = {lane.attrib['id']: lane for lane in net.findall('edge/lane')}
    outgoing = defaultdict(list)
    for link in net.findall('connection'):
        outgoing[lane_pair(link)[0]].append(link)

    def path(link):
        _, destination = lane_pair(link)
        parts, seen = [], set()
        while via := link.get('via'):
            if via in seen:
                raise ValueError(f'Ciclo de carriles internos hacia {destination}')
            seen.add(via)
            options = [item for item in outgoing[via] if lane_pair(item)[1] == destination]
            if len(options) != 1:
                raise ValueError(f'Continuación interna ausente o ambigua para {via} hacia {destination}')
            link = options[0]
            parts.append((via, attributes(lanes[via], {'id', 'index'}),
                          attributes(link, {'from', 'to', 'fromLane', 'toLane', 'via', 'tl', 'linkIndex'})))
        return tuple(parts)

    exterior = [edge for edge in net.findall('edge[@from]') if not edge.attrib['id'].startswith(':')]
    edges = {edge.attrib['id']: (attributes(edge), tuple(sorted(attributes(lane) for lane in edge.findall('lane'))))
             for edge in exterior}
    links, controller_groups, final_lanes = Counter(), defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for origin, connections in outgoing.items():
        if origin.startswith(':'):
            continue
        for link in connections:
            pair = lane_pair(link)
            parts = path(link)
            links[(pair, attributes(link, {'via', 'tl', 'linkIndex'}), tuple(part[1:] for part in parts))] += 1
            if parts:
                final_lanes[parts[-1][0]].append(pair)
            if link.get('tl') is not None:
                controller_groups[link.attrib['tl']][int(link.attrib['linkIndex'])].append(pair)

    programs = Counter()
    declared = {logic.attrib['id'] for logic in net.findall('tlLogic')}
    if controller_groups.keys() - declared:
        raise ValueError('Hay movimientos referenciando un controlador sin programa.')
    for logic in net.findall('tlLogic'):
        groups = controller_groups[logic.attrib['id']]
        mapped = tuple(sorted((tuple(sorted(pairs)), index) for index, pairs in groups.items()))
        phases = []
        for phase in logic.findall('phase'):
            states = phase.attrib['state']
            if set(groups) != set(range(len(states))):
                raise ValueError(f'Faltan enlaces para interpretar la fase de {logic.attrib["id"]}')
            phases.append((attributes(phase, {'state'}), tuple((pairs, states[index]) for pairs, index in mapped)))
        if not phases:
            raise ValueError(f'El controlador {logic.attrib["id"]} no tiene fases.')
        programs[(attributes(logic, {'id'}), tuple(phases),
                  tuple(sorted(attributes(param) for param in logic.findall('param'))))] += 1
    rings = Counter(tuple(sorted(ring.attrib['edges'].split())) for ring in net.findall('roundabout'))
    junctions = {}
    for junction in net.findall('junction'):
        if junction.attrib['id'].startswith(':'):
            continue
        internal = junction.get('intLanes', '').split()
        identities = [tuple(sorted(final_lanes[lane])) for lane in internal]
        requests = Counter()
        for request in junction.findall('request'):
            index = int(request.attrib['index'])
            relations = []
            for relation in ('foes', 'response'):
                bits = request.attrib[relation][::-1]
                if len(bits) != len(identities) or not all(identities):
                    raise ValueError(f'Matriz de conflictos sin correspondencia para {junction.attrib["id"]}')
                relations.append(tuple(sorted(identity for identity, bit in zip(identities, bits) if bit == '1')))
            requests[(identities[index], request.get('cont'), *relations)] += 1
        junctions[junction.attrib['id']] = (attributes(junction, {'incLanes', 'intLanes'}), requests)
    location = net.find('location')
    return {'projection': attributes(location, {'convBoundary', 'origBoundary'}),
            'edges': edges, 'junctions': junctions, 'connections': links, 'programs': programs, 'roundabouts': rings}


class BaselineV001(unittest.TestCase):
    def reference(self, name):
        spec = BASELINE['references'][name]
        directory = ROOT / spec['path']
        if not directory.is_dir():
            if os.environ.get('URBANFLOW_BASELINE_STRICT') == '1':
                self.fail(f'Falta la referencia requerida {spec["path"]}')
            self.skipTest(f'Falta {spec["path"]}. Ver docs/BASELINE_TECNICA_V001.md')
        for filename, expected in spec['hashes'].items():
            file = directory / filename
            self.assertTrue(file.is_file(), f'Falta el artefacto de referencia {file}')
            self.assertEqual(sha256(file.read_bytes()).hexdigest(), expected, str(file))
        return directory

    def test_ninety_three_historical_files(self):
        manifest = json.loads((ROOT / "tests/fixtures/historicos_93.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["count"], 93)
        self.assertEqual(len(manifest["files"]), 93)
        paths = [item["path"] for item in manifest["files"]]
        self.assertEqual(len(paths), len(set(paths)))
        for name, spec in BASELINE["references"].items():
            for filename, expected in spec["hashes"].items():
                listed = next(item for item in manifest["files"] if item["path"] == f"{spec['path']}/{filename}")
                self.assertEqual(listed["sha256"], expected, name)
        for item in manifest["files"]:
            file = ROOT / item["path"]
            self.assertTrue(file.is_file(), item["path"])
            self.assertEqual(sha256(file.read_bytes()).hexdigest(), item["sha256"], item["path"])

    def test_bundled_snapshot_identity(self):
        snapshot = ROOT / 'sumo_scenario/regional/maldonado.osm.gz'
        self.assertEqual(sha256(snapshot.read_bytes()).hexdigest(), BASELINE['snapshotSha256'])
        with gzip.open(snapshot, 'rb') as stream:
            _, root = next(ET.iterparse(stream, events=('start',)))
            self.assertEqual(root.attrib['snapshot'], BASELINE['snapshot'])

    def test_signature_rejects_incomplete_network(self):
        with self.assertRaisesRegex(ValueError, 'red SUMO compilada'):
            network_signature(ET.fromstring('<net><location/></net>'))

    def test_honduras_permissions_and_recorded_cycle(self):
        directory = self.reference('honduras')
        spec = BASELINE['honduras']
        net = ET.parse(directory / 'network.net.xml')
        metadata = json.loads((directory / 'metadata.json').read_bytes())
        self.assertEqual(metadata['crossingControlRevision'], 2)
        self.assertEqual(metadata['regionalMap']['snapshot'], BASELINE['snapshot'])
        self.assertFalse(set(spec['osmNodes']) & {item.attrib['id'] for item in net.findall('junction')})
        program, = net.findall('tlLogic')
        controller = program.attrib['id']
        self.assertEqual((program.attrib['type'], float(program.attrib['offset'])), ('static', 0))
        phases = program.findall('phase')
        self.assertEqual([float(phase.attrib['duration']) for phase in phases], spec['durationsSeconds'])
        exported = ET.parse(directory / 'crossing-programs.tll.xml').find('tlLogic')
        self.assertEqual(attributes(program), attributes(exported))
        self.assertEqual([attributes(phase) for phase in phases],
                         [attributes(phase) for phase in exported.findall('phase')])
        controlled = net.findall(f'connection[@tl="{controller}"]')
        self.assertEqual(len(controlled), 16)
        self.assertEqual(len({(link.attrib['from'], link.attrib['to']) for link in controlled}), 12)
        self.assertEqual({'>'.join(lane_pair(link)): [link.attrib['dir'], ''.join(
            phase.attrib['state'][int(link.attrib['linkIndex'])] for phase in phases
        )] for link in controlled}, spec['movements'])
        end_times = []
        for duration in spec['durationsSeconds']:
            end_times.append(duration + (end_times[-1] if end_times else 0))
        recorded = [item for item in ET.parse(directory / 'signal-states.xml').findall('tlsState')
                    if item.attrib['id'] == controller and float(item.attrib['time']) < end_times[-1]]
        self.assertEqual([float(item.attrib['time']) for item in recorded], [i / 2 for i in range(162)])
        for item in recorded:
            index = next(i for i, end in enumerate(end_times) if float(item.attrib['time']) < end)
            self.assertEqual(item.attrib['state'], phases[index].attrib['state'])

    def test_camacho_polygon_and_straight_connection(self):
        directory = self.reference('camacho')
        node_id = '1360039545'
        net = ET.parse(directory / 'network.net.xml')
        patch_node = ET.parse(ROOT / 'sumo_scenario/corrections/camacho.nod.xml').find(f'node[@id="{node_id}"]')
        plain_node = ET.parse(directory / 'map.nod.xml').find(f'node[@id="{node_id}"]')
        junction = net.find(f'junction[@id="{node_id}"]')
        self.assertEqual(junction.get('customShape'), '1')
        expected = patch_node.attrib['shape'].split()
        actual = plain_node.attrib['shape'].split()
        if actual[0] == actual[-1]:
            actual.pop()
        self.assertEqual(len(actual), len(expected))
        for left, right in zip(actual, expected):
            self.assertTrue(all(math.isclose(float(a), float(b), rel_tol=0, abs_tol=2e-7)
                                for a, b in zip(left.split(','), right.split(','))))
        connections = net.findall('connection[@from="-178119926#0"][@to="121506103#0"]')
        self.assertEqual([(lane_pair(link), link.attrib['dir']) for link in connections],
                         [(('-178119926#0_0', '121506103#0_0'), 's')])
        self.assertFalse([finding for finding in reversed_straights(net)
                          if finding['fromLane'] == '-178119926#0_0' and finding['toLane'] == '121506103#0_0'])

    def test_old_replays_keep_their_original_control(self):
        for name, prefix, phase_count in [('honduras_historico_fisico', 'cluster_', 12),
                                          ('honduras_historico_logico', 'joinedS_', 4)]:
            with self.subTest(reference=name):
                directory = self.reference(name)
                replay = directory / 'replay.json'
                original = json.loads(replay.read_bytes())
                program, = ET.parse(directory / 'network.net.xml').findall('tlLogic')
                self.assertTrue(program.attrib['id'].startswith(prefix))
                self.assertEqual(len(program.findall('phase')), phase_count)
                handler = SimpleNamespace(path=f'/api/studies/{directory.name}/replay',
                                          respond=lambda status, data: (status, data))
                with patch.object(study_server, 'STUDIES', directory.parent):
                    status, response = study_server.StudyHandler.do_GET(handler)
                self.assertEqual(status, 200)
                self.assertTrue(response['legacyCrossingControl'])
                self.assertEqual(response['signalReplay'], original['signalReplay'])
                self.assertEqual(response['frames'], original['frames'])
                self.assertEqual(sha256(replay.read_bytes()).hexdigest(),
                                 BASELINE['references'][name]['hashes']['replay.json'])

    def test_candidate_networks(self):
        candidates = {name: os.environ.get(f'URBANFLOW_BASELINE_{name.upper()}')
                      for name in ('honduras', 'camacho')}
        if not any(candidates.values()) and os.environ.get('URBANFLOW_BASELINE_STRICT') != '1':
            self.skipTest('Faltan las redes candidatas de Honduras y Camacho.')
        for name, candidate in candidates.items():
            with self.subTest(reference=name):
                self.assertTrue(candidate, f'Falta URBANFLOW_BASELINE_{name.upper()}')
                original_file = self.reference(name) / 'network.net.xml'
                rebuilt_base = os.environ.get('URBANFLOW_BASELINE_BASE_CAMACHO') if name == 'camacho' else None
                reference = Path(rebuilt_base) if rebuilt_base else original_file
                candidate = Path(candidate)
                self.assertFalse(candidate.samefile(reference) or candidate.samefile(original_file),
                                 f'{name}: la candidata debe provenir de otra compilación.')
                if rebuilt_base:
                    self.assertFalse(reference.samefile(original_file), 'Camacho: la base indicada no fue recompilada.')
                original = network_signature(ET.parse(reference))
                proposed = network_signature(ET.parse(candidate))
                for section in original:
                    self.assertEqual(original[section], proposed[section], section)

    def test_signature_ignores_internal_labels_and_signal_slot_numbers(self):
        directory = self.reference('honduras')
        net = ET.parse(directory / 'network.net.xml').getroot()
        reference = network_signature(net)
        candidate = deepcopy(net)
        # Rename internal edges and lanes consistently and swap signal slots 0/2.
        aliases = {item.attrib['id']: item.attrib['id'].replace(':', ':rename-', 1)
                   for item in candidate.findall('.//*[@id]') if item.attrib['id'].startswith(':')}
        for item in candidate.iter():
            for key, value in item.attrib.items():
                if key in {'id', 'from', 'to', 'via', 'incLanes', 'intLanes'}:
                    item.set(key, ' '.join(aliases.get(word, word) for word in value.split()))
            if item.tag == 'tlLogic':
                item.set('id', 'renamed-controller')
            if item.tag == 'connection' and item.get('tl'):
                item.set('tl', 'renamed-controller')
                if item.attrib['linkIndex'] in ('0', '2'):
                    item.set('linkIndex', '2' if item.attrib['linkIndex'] == '0' else '0')
            if item.tag == 'phase':
                state = list(item.attrib['state'])
                state[0], state[2] = state[2], state[0]
                item.set('state', ''.join(state))
        self.assertNotEqual(ET.tostring(net), ET.tostring(candidate))
        self.assertEqual(reference, network_signature(candidate))
        changed = deepcopy(candidate)
        edge = changed.find('edge[@id="426635857"]')
        edge.set('from', edge.attrib['to'])
        self.assertNotEqual(reference['edges'], network_signature(changed)['edges'])
        changed = deepcopy(candidate)
        phase = changed.find('tlLogic/phase[@duration="20"]')
        phase.set('state', phase.attrib['state'].replace('G', 'g', 1))
        self.assertNotEqual(reference['programs'], network_signature(changed)['programs'])
        changed = deepcopy(candidate)
        request = changed.find('junction[@type="traffic_light"]/request')
        response = request.attrib['response']
        request.set('response', ('1' if response[0] == '0' else '0') + response[1:])
        self.assertNotEqual(reference['junctions'], network_signature(changed)['junctions'])


class KnownLimitationsV001(unittest.TestCase):
    """Characterize current behavior. A later intentional fix must update these assertions."""

    def test_h03_edge_path_loses_lane_continuity(self):
        net = ET.fromstring('''<net>
          <edge id="a" from="u" to="v"><lane index="0" length="20"/></edge>
          <edge id="b" from="v" to="w">
            <lane index="0" length="1" changeLeft="none"/>
            <lane index="1" length="1" changeRight="none"/>
          </edge>
          <edge id="c" from="w" to="x"><lane index="0" length="20"/></edge>
          <connection from="a" to="b" fromLane="0" toLane="0"/>
          <connection from="b" to="c" fromLane="1" toLane="0"/>
        </net>''')
        incoming, outgoing = net.findall('connection')
        self.assertNotEqual(incoming.attrib['toLane'], outgoing.attrib['fromLane'])
        self.assertEqual(net.find('edge[@id="b"]/lane[@index="0"]').attrib['changeLeft'], 'none')
        _, forward, _ = read_network(net, 'passenger')
        self.assertIn('b', forward['a'])
        self.assertIn('c', forward['b'])

    def test_h06_planned_uses_full_demand_but_arrivals_use_common_horizon(self):
        network = '<net><edge id="in"><lane id="in_0" length="100"/></edge></net>'
        route = {'id': 'in:out:car', 'entry': 'in', 'from': 'Entrada', 'kind': 'car', 'routes': [['in', 'out']]}
        with TemporaryDirectory() as temp:
            runs = []
            for name, seconds, late in [('short', 60, False), ('long', 180, True)]:
                directory = Path(temp) / name
                directory.mkdir()
                runs.append(directory)
                (directory / 'network.net.xml').write_text(network, encoding='utf-8')
                (directory / 'traffic-catalog.json').write_text(json.dumps([route]), encoding='utf-8')
                count = 2 if late else 1
                metadata = {'title': 'Sintético H06', 'osmNodes': ['1'], 'seconds': seconds,
                            'traffic': {'source': 'sample', 'durationMinutes': 2 if late else 1,
                                        'movements': [{'id': route['id'], 'count': count}]}}
                (directory / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
                flows = '<flow id="early" type="car" route="r" begin="10" end="11" number="1"/>'
                trips = '<tripinfo id="early.0" arrival="30" waitingTime="5"/>'
                if late:
                    flows += '<flow id="late" type="car" route="r" begin="90" end="91" number="1"/>'
                    trips += '<tripinfo id="late.0" arrival="120" waitingTime="25"/>'
                (directory / 'routes.rou.xml').write_text(
                    f'<routes><vType id="car" length="5"/><route id="r" edges="in out"/>{flows}</routes>',
                    encoding='utf-8')
                (directory / 'trips.xml').write_text(f'<tripinfos>{trips}</tripinfos>', encoding='utf-8')
                (directory / 'trajectories.xml').write_text(
                    '<fcd-export><timestep time="0"/></fcd-export>', encoding='utf-8')
            report = compare_studies(*runs)
            self.assertEqual(report['seconds'], 60)
            short, long = report['runs']
            self.assertEqual((short['planned'], short['completed']), (1, 1))
            self.assertEqual((long['planned'], long['completed']), (2, 1))
            self.assertEqual(long['accesses'][0]['meanWaitSeconds'], 5)


if __name__ == '__main__':
    unittest.main()
