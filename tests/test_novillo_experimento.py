"""La comparación 1G.3 se detiene porque los recorridos no comparten destino SUMO."""

from hashlib import sha256
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

import tools.novillo_experimento as experimento


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "results/_tmp/etapa1g3"
CERTIFIED = ROOT / "results/_tmp/etapa1g1/red.net.xml"
PUBLIC = ROOT / "urbanflow-web/assets/novillo-experimento.json"
REPLAY = ROOT / "results/etapa1c5-sector01/candidata/01c5b202611140000000000000000001/replay.json"
SNAPSHOT = ROOT / "sumo_scenario/regional/maldonado.osm.gz"
CERTIFIED_SHA256 = "3636e0efc5f2856fe38ca011e9f103746f27c975620424ad11b1e8e59bafa108"
REPLAY_SHA256 = "03b534e910cd373360eb595fa463dff5e7ee9f743368b67378c7e6aca141080b"
SNAPSHOT_SHA256 = "868b473a814999649af1d03ba164be232320c9dd82a229d5514315c0afc3a272"


def digest(path):
    hashed = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


class NovilloExperimentTest(unittest.TestCase):
    def test_routes_are_legal_and_do_not_share_a_sumo_destination(self):
        checked = experimento.assess(STAGE / "red.net.xml")
        published = json.loads(PUBLIC.read_text(encoding="utf-8"))
        self.assertTrue(checked["throughLegal"])
        self.assertTrue(checked["avoidLegal"])
        self.assertEqual(checked["originEdge"], "983235082")
        self.assertEqual(checked["originNode"], "1155355178")
        self.assertEqual(checked["destinationNode"], "3175611488")
        self.assertEqual(checked["throughArrivalEdges"], ["983236122"])
        self.assertEqual(checked["avoidArrivalEdges"], ["454567064"])
        self.assertIn("-252069937", checked["avoidEdges"])
        self.assertIn("101195613", checked["avoidEdges"])
        self.assertNotIn("100089298", checked["avoidWays"])
        self.assertIn("100089298", checked["throughWays"])
        self.assertEqual(checked["sharedDestinationEdges"], [])
        self.assertEqual(checked["sharedContinuationEdges"], [])
        self.assertEqual(checked["franciaConnection"], [])
        self.assertTrue(checked["samePhysicalNode"])
        self.assertTrue(checked["bidirectionalPedragosa"])
        self.assertEqual(published["routes"]["throughEdges"], checked["throughEdges"])
        self.assertEqual(published["routes"]["avoidEdges"], checked["avoidEdges"])
        self.assertIsNone(published["comparison"])
        self.assertIsNone(published["simulated"])
        self.assertTrue(published["experimental"])
        self.assertFalse(published["calibrated"])
        self.assertFalse(published["seasonal"])
        self.assertEqual(published["restriction"][0]["id"], "6890666")
        self.assertEqual(published["restriction"][0]["type"], "no_left_turn")
        self.assertEqual(published["arrivals"][0]["continuations"], [])
        self.assertEqual(published["arrivals"][1]["continuations"][0]["to"], "311824953")
        self.assertEqual(published["speedAssumption"]["kmh"], 30)
        self.assertFalse(published["speedAssumption"]["signage"])
        self.assertFalse(published["speedAssumption"]["usedInSimulation"])
        self.assertEqual(published["speedAssumption"]["ringMetersPerSecondBefore"], ["27.78"])

    def test_candidate_does_not_touch_certified_files(self):
        net = ET.parse(STAGE / "red.net.xml").getroot()
        speeds = {lane.get("speed") for lane in net.iter("lane")}
        self.assertEqual(speeds, {"8.33"})
        edge_ids = {edge.get("id") for edge in net.findall("edge")}
        self.assertIn("-252069937", edge_ids)
        self.assertIn("-101195613", edge_ids)
        self.assertIn("101195613", edge_ids)
        ends = {(edge.get("from"), edge.get("to")) for edge in net.findall("edge")}
        self.assertNotIn(("1156825106", "1155354703"), ends)
        self.assertNotIn(("1155354703", "1156825106"), ends)
        for name in ("routes.rou.xml", "trips.xml", "tripinfo.xml", "edgedata.xml", "fcd.xml"):
            self.assertFalse((STAGE / name).exists())
        certified = CERTIFIED.read_text(encoding="utf-8")
        self.assertNotIn("252069937", certified)
        self.assertNotIn("101195613", certified)
        self.assertEqual(digest(CERTIFIED), CERTIFIED_SHA256)
        self.assertEqual(digest(REPLAY), REPLAY_SHA256)
        self.assertEqual(REPLAY.stat().st_size, 1084990)
        self.assertEqual(digest(SNAPSHOT), SNAPSHOT_SHA256)
