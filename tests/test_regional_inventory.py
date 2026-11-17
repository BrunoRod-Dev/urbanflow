from collections import defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET

from sumo_scenario.regional_inventory import build, direction, interior_faces, restriction_candidates, road_graph, road_segments, route


ROOT = Path(__file__).resolve().parents[1]


class RegionalInventoryTest(unittest.TestCase):
    def test_explicit_and_inferred_senses(self):
        self.assertEqual(direction({'oneway': '-1'}), 'reverse')
        self.assertEqual(direction({'junction': 'roundabout'}), 'inferred-forward')
        self.assertEqual(direction({'junction': 'roundabout', 'oneway': 'no'}), 'both')
        self.assertEqual(direction({'oneway:conditional': 'yes @ (Mo-Fr)'}), 'unknown')

    def test_missing_geometry_does_not_create_a_shortcut(self):
        points = {'a': (0, 0), 'b': (1, 0)}
        way = ET.fromstring('<way><tag k="highway" v="residential"/></way>')
        segments, missing = road_segments({'7': (way, ['a', 'missing', 'b'])}, points)
        self.assertEqual(missing, ['7:0', '7:1'])
        self.assertEqual(segments, {})

    def test_route_respects_oneway_and_private_access(self):
        points = {'a': (0, 0), 'b': (1, 0), 'c': (2, 0)}
        segments = {'1:0': ('1', 'a', 'b', {'highway': 'secondary', 'oneway': 'yes'}),
                    '2:0': ('2', 'b', 'c', {'highway': 'secondary', 'access': 'private'})}
        graph = road_graph(segments, points)
        self.assertEqual(route(graph, segments, 'a', 'b', []), [('1:0', 'a', 'b')])
        for start, end in [('b', 'a'), ('a', 'c')]:
            with self.assertRaises(ValueError):
                route(graph, segments, start, end, [])

    def test_perimeter_does_not_close_an_open_chain(self):
        points = {'a': (0, 0), 'b': (1, 0), 'c': (0, 1), 'd': (2, 0)}
        chain = [('1:0', 'a', 'b'), ('1:1', 'b', 'c')]
        self.assertTrue(interior_faces([chain], points)[0].is_empty)
        closed = chain + [('2:0', 'c', 'a'), ('3:0', 'b', 'd'), ('3:0', 'd', 'b')]
        faces, _, dangles, invalid = interior_faces([closed], points)
        self.assertEqual(len(faces.geoms), 1)
        self.assertEqual(len(dangles.geoms), 1)
        self.assertTrue(invalid.is_empty)

    def test_turn_restriction_review(self):
        segments = {'1:0': ('1', 'a', 'b', {}), '2:0': ('2', 'b', 'c', {})}
        relation = {'osmRelation': '8', 'tags': {'restriction': 'no_left_turn'}, 'members': [
            {'role': 'from', 'type': 'way', 'ref': '1'}, {'role': 'via', 'type': 'node', 'ref': 'b'},
            {'role': 'to', 'type': 'way', 'ref': '2'}]}
        self.assertEqual(restriction_candidates([('1:0', 'a', 'b'), ('2:0', 'b', 'c')], segments, [relation]), ['8'])

    def test_v002_connects_solanas_with_two_real_directed_circuits(self):
        from shapely.geometry import shape

        report, features = self.v002
        rows = {row['id']: row for row in report['corridors']}
        roads = {f['properties']['id']: f['properties'] for f in features if f['properties']['kind'] == 'road-segment'}
        expanded = {key for key, properties in roads.items() if properties.get('preserveFor')}
        hub = '1761794826'
        for key in ('mansa', 'lussich'):
            self.assertEqual(rows[key]['steps'][-1][2], hub)
        for key in ('solanas-sur', 'solanas-norte'):
            steps = rows[key]['steps']
            self.assertEqual(steps[0][1], hub)
            self.assertEqual(steps[-1][2], hub)
            self.assertEqual(len({a for _, a, _ in steps}), len(steps))
            self.assertTrue(all(left[2] == right[1] for left, right in zip(steps, steps[1:])))
            for segment, start, end in steps:
                road = roads[segment]
                self.assertTrue(road['location'] != 'outside' or segment in expanded)
                sense = road['direction']
                if sense in ('forward', 'inferred-forward'):
                    self.assertEqual([start, end], road['osmNodes'])
                elif sense == 'reverse':
                    self.assertEqual([end, start], road['osmNodes'])
                else:
                    self.assertIn(sense, ('both', 'inferred-both'))
            faces = [shape(f['geometry']) for f in features if f['properties'].get('boundaryGroup') == key]
            self.assertEqual(len(faces), 1)
            self.assertTrue(faces[0].is_valid)
            self.assertGreater(faces[0].area, 0)
        self.assertEqual(len(report['selection']['weakComponents']), 1)

    def test_v002_checks_selected_turns_and_preserves_complete_roundabout(self):
        report, features = self.v002
        joins = {row['id']: row for row in report['junctions']}
        for name, ways in {
            'cabecera-este-leonel-viera': ['29235037', '184300539'],
            'la-barra-a-punta-del-este': ['182082909', '184300558'],
            'saravia-al-anillo': ['100719068', '100719054'],
            'anillo-a-herrera': ['100719054', '362483925'],
            'mansa-a-solanas-sur': ['185325837', '185325886'],
            'solanas-sur-a-interbalnearia': ['164559156', '185325837'],
            'solanas-norte-ruta-12': ['115675908', '164559170'],
        }.items():
            self.assertEqual(joins[name]['wayIds'], ways)
            self.assertFalse(joins[name]['restrictionReview'])

        ring = next(row for row in report['roundabouts'] if '1428227104' in row['ringWays'])
        self.assertEqual(set(ring['ringWays']), {'1207049875', '1428227104', '1428227105',
                                               '1428227106', '1428227107', '1428227113'})
        self.assertTrue(ring['completeDirectedCycle'])
        self.assertFalse(ring['missingNodes'])
        self.assertGreater(ring['outsideRingSegments'], 0)
        ways = defaultdict(list)
        for feature in features:
            if feature['properties']['kind'] == 'road-segment':
                ways[feature['properties']['osmWay']].append(feature['properties'])
        for way in ring['preserveWays']:
            self.assertTrue(ways[way])
            self.assertTrue(all(road['location'] != 'outside' or road.get('preserveFor') for road in ways[way]))

    def test_v002_prefers_contiguous_camino_lussich_and_rejoins_near_arboretum(self):
        report, features = self.v002
        rows = {row['id']: row for row in report['corridors']}
        roads = {f['properties']['id']: f['properties'] for f in features if f['properties']['kind'] == 'road-segment'}
        selected = rows['lussich']['steps']
        camino = [i for i, (key, _, _) in enumerate(selected) if roads[key]['tags'].get('name') == 'Camino Lussich']
        self.assertTrue(camino)
        self.assertEqual(camino, list(range(camino[0], camino[-1] + 1)))
        self.assertIn('2367503408', [b for _, _, b in selected[camino[-1] + 1:]])
        self.assertNotIn('Camino Lussich', rows['lussich-avenida-alternativa']['names'])

    @classmethod
    def setUpClass(cls):
        plan = json.loads((ROOT / 'sumo_scenario/regional/corridors-v002.json').read_bytes())
        with TemporaryDirectory() as temp:
            output = Path(temp) / 'inventory'
            build(plan, output)
            cls.v002 = (json.loads((output / 'inventory.json').read_bytes()),
                        json.loads((output / 'inventory.geojson').read_bytes())['features'])

    def test_snapshot_inventory_has_connected_corridors_and_interior(self):
        plan = json.loads((ROOT / 'sumo_scenario/regional/corridors-v001.json').read_bytes())
        with TemporaryDirectory() as temp:
            output = Path(temp) / 'inventory'
            build(plan, output)
            report = json.loads((output / 'inventory.json').read_bytes())
            self.assertGreater(report['interiorWays'], 0)
            self.assertGreater(report['perimeter']['faces'], 0)
            self.assertFalse(report['missingGeometrySegments'])
            for row in report['corridors']:
                self.assertEqual(row['steps'][0][1], row['anchors'][0])
                self.assertEqual(row['steps'][-1][2], row['anchors'][-1])
                self.assertTrue(all(left[2] == right[1] for left, right in zip(row['steps'], row['steps'][1:])))
