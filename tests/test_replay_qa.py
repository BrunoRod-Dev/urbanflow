from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sumo_scenario.replay_qa import Audit, Sample, compare_runs, lane_path_exists, signed_turn


class ReplayQaTests(unittest.TestCase):
    def test_missing_and_changed_repetition_are_distinct_from_match(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            a, b = (base / key for key in ('a', 'b'))
            a.mkdir()
            b.mkdir()
            for index, directory in enumerate((a, b)):
                (directory / 'summary.xml').write_text(f'<summary><step time="1" duration="{index}"/></summary>')
                (directory / 'trips.xml').write_text(f'<tripinfos><tripinfo arrival="{index}"/></tripinfos>')
            result = compare_runs(a, b)
            self.assertEqual(result['summary.xml']['status'], 'match')
            self.assertEqual(result['trips.xml']['status'], 'different')
            self.assertEqual(result['collisions.xml']['status'], 'missing')

    def test_no_vehicle_or_time_is_fabricated_for_a_static_shape(self):
        audit = Audit.__new__(Audit)
        audit.events = []
        audit.lanes = {':j_0_0': {'edge': ':j_0'}}
        audit.internal_nodes = {':j_0_0': 'j'}
        audit.positions = {'j': [-54, -34]}
        event = audit.add('reverse_geometry', 'warning', 'static', 'Geometry', {}, lane=':j_0_0')
        self.assertEqual((event['edge'], event['node'], event['coordinates']), (':j_0', 'j', [-54, -34]))
        self.assertIsNone(event['time'])
        self.assertIsNone(event['vehicleId'])

    def test_heading_wrap_and_same_lane_position_regression(self):
        self.assertEqual(signed_turn(359, 1), 2)
        audit = Audit.__new__(Audit)
        audit.events = []
        audit.lanes = {}
        audit.geo = False
        audit.check_sample_pair('car', Sample(1, 'lane', 4, 2, 359, 0, 0),
                                Sample(1.5, 'lane', 3, 2, 1, 0, -1))
        self.assertEqual([e['kind'] for e in audit.events], ['lane_position_reverse'])
        self.assertEqual(audit.events[0]['time'], 1.5)
        self.assertIsNone(audit.events[0]['coordinates'])

    def test_continuity_can_cross_internal_and_short_unsampled_lane(self):
        lanes = {key: {'edge': edge} for key, edge in
                 [('a', 'A'), ('x', ':J'), ('b', 'B'), ('y', ':K'), ('c', 'C')]}
        links = {'a': ['x'], 'x': ['b'], 'b': ['y'], 'y': ['c']}
        self.assertTrue(lane_path_exists('a', 'c', links, {'A', 'B', 'C'}, lanes, {}))
        self.assertFalse(lane_path_exists('a', 'c', links, {'A', 'C'}, lanes, {}))


if __name__ == '__main__':
    unittest.main()
