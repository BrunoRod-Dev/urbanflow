"""UTM de SUMO: la candidata 1C.5 no se recalcula y las redes extensas conservan un solo marco."""

from hashlib import sha256
from math import cos, hypot, radians
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import xml.etree.ElementTree as ET

from sumo_scenario.geo_projection import (
    ProjectionError, projection_from_network, to_geographic, to_sumo,
)
from sumo_scenario.lane_geometry import geographic_transform

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "results/etapa1c5-sector01/candidata"
REPLAY_ID = "01c5b202611140000000000000000001"


def meters(lng, lat, actual_lng, actual_lat):
    return hypot((lng - actual_lng) * cos(radians(actual_lat)), lat - actual_lat) * 111_320


def location_element(proj, offset, orig, conv):
    root = ET.Element("net")
    ET.SubElement(root, "location", projParameter=proj,
                  netOffset=f"{offset[0]},{offset[1]}",
                  origBoundary=",".join(str(value) for value in orig),
                  convBoundary=",".join(str(value) for value in conv))
    return root


def square(side, lon=-54.94, lat=-34.95, zone=21, false_northing=0.0, south_flag=False):
    from sumo_scenario.geo_projection import _forward_equator, _inverse_equator
    center_e, center_n = _forward_equator(lon, lat, zone)
    offset = (-(center_e - side / 2), -(center_n - side / 2) - false_northing)

    def geo(x, y):
        return _inverse_equator(x - offset[0], y - offset[1] - false_northing, zone)

    corners = [geo(x, y) for x, y in ((0, 0), (side, 0), (0, side), (side, side))]
    orig = (min(p[0] for p in corners), min(p[1] for p in corners),
            max(p[0] for p in corners), max(p[1] for p in corners))
    proj = f"+proj=utm +zone={zone} +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
    if south_flag:
        proj += " +south"
    network = location_element(proj, offset, orig, (0, 0, side, side))
    return projection_from_network(network), geo


def grid_network(side, step):
    projection, geo = square(side)
    root = ET.Element("net")
    nodes = ET.Element("nodes")
    index = 0
    for x in range(0, int(side) + 1, step):
        for y in range(0, int(side) + 1, step):
            identifier = str(index)
            lng, lat = geo(x, y)
            ET.SubElement(root, "junction", id=identifier, x=str(x), y=str(y))
            ET.SubElement(nodes, "node", id=identifier, x=f"{lng:.7f}", y=f"{lat:.7f}")
            index += 1
    return ET.ElementTree(root), ET.ElementTree(nodes), projection


class GeoProjectionTests(unittest.TestCase):
    def test_certified_candidate_keeps_its_affine_replay(self):
        manifest_path = CANDIDATE / "manifest.json"
        replay_path = CANDIDATE / REPLAY_ID / "replay.json"
        network_path = CANDIDATE / REPLAY_ID / "network.net.xml"
        nodes_path = CANDIDATE / REPLAY_ID / "map.nod.xml"
        self.assertTrue(manifest_path.is_file(), "Falta la candidata certificada de 1C.5.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = sha256(replay_path.read_bytes()).hexdigest()
        self.assertEqual(digest, manifest["artifacts"][f"{REPLAY_ID}/replay.json"])
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        stored = replay["laneMotion"]["projection"]
        fresh = geographic_transform(ET.parse(network_path), nodes_path)
        self.assertEqual(stored["origin"], list(fresh["origin"]))
        self.assertEqual(stored["location"], list(fresh["location"]))
        self.assertEqual(stored["east"], fresh["east"])
        self.assertEqual(stored["north"], fresh["north"])
        self.assertNotIn("type", stored)

    def test_utm_matches_the_317_certified_junctions_within_one_centimeter(self):
        network_path = CANDIDATE / REPLAY_ID / "network.net.xml"
        nodes_path = CANDIDATE / REPLAY_ID / "map.nod.xml"
        self.assertTrue(network_path.is_file(), "Falta la red certificada de 1C.5.")
        network = ET.parse(network_path)
        projection = projection_from_network(network)
        self.assertEqual(projection["type"], "utm")
        self.assertEqual(projection["zone"], 21)
        self.assertEqual(projection["falseNorthing"], 0.0)
        self.assertNotIn("east", projection)
        nodes = {node.get("id"): (float(node.get("x")), float(node.get("y")))
                 for node in ET.parse(nodes_path).findall("node")}
        errors = []
        for junction in network.findall("junction"):
            identifier = junction.get("id")
            if identifier not in nodes:
                continue
            predicted = to_geographic((float(junction.get("x")), float(junction.get("y"))), projection)
            actual = nodes[identifier]
            errors.append(meters(*predicted, *actual))
        self.assertEqual(len(errors), 317)
        self.assertLess(max(errors), 0.01, f"error máximo {max(errors):.4f} m")

    def test_extended_squares_keep_one_frame_where_the_affine_fit_fails(self):
        for side in (3000, 10000, 30000):
            with self.subTest(side=side):
                network, nodes, projection = grid_network(side, side // 4)
                directory = TemporaryDirectory()
                self.addCleanup(directory.cleanup)
                node_file = Path(directory.name) / "map.nod.xml"
                nodes.write(node_file, encoding="utf-8")
                self.assertIsNone(geographic_transform(network, node_file))
                worst = 0
                for junction in network.findall("junction"):
                    point = (float(junction.get("x")), float(junction.get("y")))
                    lng, lat = to_geographic(point, projection)
                    back = to_sumo(lng, lat, projection)
                    worst = max(worst, hypot(back[0] - point[0], back[1] - point[1]))
                self.assertLess(worst, 0.01)

    def test_overlapping_windows_share_sumo_coordinates(self):
        projection, geo = square(10000)
        shared = geo(5000, 5000)
        other = geo(6500, 4200)
        windows = ((geo(2000, 5000), geo(4000, 5000)), (geo(7000, 5000), geo(9000, 5000)))

        def scene_delta(center):
            origin = to_sumo(*center, projection)
            first = to_sumo(*shared, projection)
            second = to_sumo(*other, projection)
            return (second[0] - first[0], second[1] - first[1], first[0] - origin[0], first[1] - origin[1])

        left, right = (scene_delta(center) for center in (windows[0][0], windows[1][0]))
        self.assertAlmostEqual(left[0], right[0], places=6)
        self.assertAlmostEqual(left[1], right[1], places=6)
        self.assertGreater(abs(left[2] - right[2]) + abs(left[3] - right[3]), 1000)

    def test_false_northing_follows_the_proj_string_and_the_offset(self):
        northern, _ = square(1000, lon=13.4, lat=52.5, zone=33, false_northing=0.0)
        self.assertEqual(northern["zone"], 33)
        self.assertEqual(northern["falseNorthing"], 0.0)
        southern, geo = square(1000, false_northing=10_000_000.0, south_flag=True)
        self.assertEqual(southern["falseNorthing"], 10_000_000.0)
        lng, lat = geo(250, 250)
        back = to_sumo(lng, lat, southern)
        self.assertLess(hypot(back[0] - 250, back[1] - 250), 0.01)

    def test_missing_and_unsupported_projections_name_the_cause(self):
        with self.assertRaises(ProjectionError) as missing:
            projection_from_network(ET.Element("net"))
        self.assertIn("no declara la proyección", str(missing.exception))
        proj = "+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs"
        with self.assertRaises(ProjectionError) as unsupported:
            projection_from_network(location_element(proj, (0, 0), (-1, -1, 1, 1), (0, 0, 1, 1)))
        self.assertIn("no está soportada", str(unsupported.exception))
        utm = "+proj=utm +zone=21 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
        with self.assertRaises(ProjectionError) as offset:
            projection_from_network(location_element(utm, (0, 0), (-54.95, -34.96, -54.93, -34.94), (0, 0, 10, 10)))
        self.assertIn("netOffset no coincide", str(offset.exception))


if __name__ == "__main__":
    unittest.main()
