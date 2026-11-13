"""Exercise every road-to-road movement through the rebuilt Honduras junction."""

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET

from sumo_scenario.compound_crossings import CROSSINGS, joined_id
from sumo_scenario.junction_index import confirmed_junction
from sumo_scenario.study import VEHICLE_TYPES, StudyError, generate_study, run_tool, sumo_tools


class HondurasControlTest(unittest.TestCase):
    def test_protected_movements_clear_the_junction(self):
        try:
            sumo, _, env = sumo_tools()
        except StudyError as error:
            self.skipTest(str(error))
        nodes = CROSSINGS[0]
        controller = joined_id(nodes)
        target = confirmed_junction('n' + nodes[0])
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            directory = Path(temp)
            generate_study(directory, *target['location'], lambda *_: None, directory, target=target)
            network = ET.parse(directory / 'network.net.xml')
            signal = network.find(f'tlLogic[@id="{controller}"]')
            self.assertIsNotNone(signal)
            self.assertTrue(all(network.find(f'junction[@id="{node}"]') is None for node in nodes))
            controlled = network.findall(f'connection[@tl="{controller}"]')
            movements = {(link.get('from'), link.get('to')) for link in controlled}
            self.assertEqual(len(movements), 12)
            self.assertFalse(any(link.get('dir') in {'t', 'T'} for link in controlled))
            states = [phase.get('state') for phase in signal.findall('phase')]
            self.assertEqual(sum(any(color in 'Gg' for color in state) for state in states), 3)
            self.assertTrue(all(any(state[int(link.get('linkIndex'))] in 'Gg' for state in states) for link in controlled))
            plain = ET.parse(directory / 'map.tll.xml').find(f'tlLogic[@id="{controller}"]')
            self.assertEqual(states, [phase.get('state') for phase in plain.findall('phase')])

            demand = ET.parse(directory / 'routes.rou.xml')
            routes = {route.get('id'): route.get('edges').split() for route in demand.iterfind('route')}
            departures = {flow.get('id'): flow.get('route') for flow in demand.iterfind('flow')}
            run_tool([sumo, '--net-file', 'network.net.xml', '--route-files', 'routes.rou.xml', '--end', '420',
                      '--seed', '42', '--step-length', '0.5', '--no-step-log', 'true', '--time-to-teleport', '-1',
                      '--collision.check-junctions', 'true', '--collision-output', 'test-collisions.xml',
                      '--fcd-output', 'test-trajectories.xml', '--tripinfo-output', 'test-trips.xml'],
                     directory, env, 'La prueba de los movimientos protegidos')
            self.assertFalse(ET.parse(directory / 'test-collisions.xml').findall('collision'))
            completed = set()
            for trip in ET.parse(directory / 'test-trips.xml').iterfind('tripinfo'):
                route = routes[departures[trip.get('id').rsplit('.', 1)[0]]]
                completed.update(set(zip(route, route[1:])) & movements)
            self.assertEqual(completed, movements)

            inside = ':' + controller + '_'
            waits = defaultdict(list)
            for frame in ET.parse(directory / 'test-trajectories.xml').iterfind('timestep'):
                for vehicle in frame.iterfind('vehicle'):
                    if vehicle.get('lane').startswith(inside) and float(vehicle.get('speed')) < .1:
                        waits[vehicle.get('id')].append(float(frame.get('time')))
            self.assertFalse(waits, dict(waits))
            self.check_blocked_exit(directory, sumo, env, inside)

    def check_blocked_exit(self, directory, sumo, env, inside):
        routes = ET.Element('routes')
        ET.SubElement(routes, 'vType', id='probe-bus', **{key: str(value) for key, value in VEHICLE_TYPES['terminal-bus'].items()})
        ET.SubElement(routes, 'route', id='blocked', edges='181384674#0 181384674#1')
        ET.SubElement(routes, 'route', id='straight', edges='426635855#0 181384674#0 181384674#1')
        for lane in ('0', '1'):
            vehicle = ET.SubElement(routes, 'vehicle', id=f'blocked-{lane}', depart='0', route='blocked',
                                    departPos='4', departLane=lane, departSpeed='0')
            ET.SubElement(vehicle, 'stop', lane=f'181384674#0_{lane}', endPos='7', until='16')
        ET.SubElement(routes, 'vehicle', id='line9-probe', depart='1', type='probe-bus', route='straight',
                      departLane='1', departSpeed='0')
        ET.ElementTree(routes).write(directory / 'blocked.rou.xml')
        run_tool([sumo, '--net-file', 'network.net.xml', '--route-files', 'blocked.rou.xml', '--end', '230',
                  '--seed', '42', '--step-length', '0.5', '--no-step-log', 'true', '--time-to-teleport', '-1',
                  '--collision.check-junctions', 'true', '--collision-output', 'blocked-collisions.xml',
                  '--fcd-output', 'blocked-trajectories.xml'], directory, env, 'La prueba con la salida ocupada')
        observations = [(float(frame.get('time')), vehicle.get('lane'), float(vehicle.get('speed')))
                        for frame in ET.parse(directory / 'blocked-trajectories.xml').iterfind('timestep')
                        for vehicle in frame.iterfind('vehicle[@id="line9-probe"]')]
        crossing = [(time, speed) for time, lane, speed in observations if lane.startswith(inside)]
        self.assertTrue(any(5 <= time < 16 and lane.startswith('426635855#0') and speed < .1
                            for time, lane, speed in observations))
        self.assertTrue(crossing)
        self.assertGreaterEqual(crossing[0][0], 16)
        self.assertTrue(all(speed > .1 for _, speed in crossing))
        self.assertFalse(ET.parse(directory / 'blocked-collisions.xml').findall('collision'))


if __name__ == '__main__':
    unittest.main()
