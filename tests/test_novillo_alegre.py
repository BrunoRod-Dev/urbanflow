"""El caso geométrico de la rotonda deja el desvío sin simular."""

from hashlib import sha256
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

import tools.novillo_alegre as novillo


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "results/_tmp/etapa1g1"
PUBLIC = ROOT / "urbanflow-web/assets/novillo-alegre.json"
GEOJSON = ROOT / "urbanflow-web/assets/novillo-alegre.geojson"
REPLAY = ROOT / "results/etapa1c5-sector01/candidata/01c5b202611140000000000000000001/replay.json"
SNAPSHOT = ROOT / "sumo_scenario/regional/maldonado.osm.gz"
REPLAY_SHA256 = "03b534e910cd373360eb595fa463dff5e7ee9f743368b67378c7e6aca141080b"
SNAPSHOT_SHA256 = "868b473a814999649af1d03ba164be232320c9dd82a229d5514315c0afc3a272"
EXCLUDED = ("185329451", "100473863", "100070328", "311824955", "101195541", "100473830")


def digest(path):
    hashed = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


class NovilloCaseTest(unittest.TestCase):
    def test_roundabout_is_verified_and_bypass_is_not(self):
        report = novillo.verify()
        ring = next(item for item in report["roundabouts"] if item["id"] == "100089298")
        self.assertTrue(ring["closed"])
        self.assertTrue(ring["counterclockwise"])
        self.assertEqual(ring["contradictions"], [])
        self.assertTrue(ring["accepted"])
        self.assertIn("100089295", ring["entries"])
        self.assertIn("29235087", ring["exits"])
        self.assertTrue(report["routes"]["through"]["legal"])
        self.assertEqual(report["routes"]["through"]["ways"][4], "100089298")
        self.assertFalse(report["routes"]["avoid"]["legal"])
        self.assertFalse(report["routes"]["avoid"]["diagnosticAccepted"])
        self.assertTrue(report["routes"]["avoid"]["diagnosticConnects"])
        self.assertEqual([item["id"] for item in report["routes"]["avoid"]["blockedBy"]], ["101195613", "252069937"])
        self.assertIsNone(report["comparison"])
        self.assertIsNone(report["simulated"])
        self.assertFalse(report["queues"]["measured"])
        self.assertFalse(report["calibrated"])
        self.assertFalse(report["seasonal"])
        self.assertTrue(report["experimental"])
        self.assertFalse(report["francia"]["joinsArtigasToPedragosa"])

    def test_compiled_network_keeps_only_verified_ways(self):
        published = json.loads(PUBLIC.read_text(encoding="utf-8"))
        self.assertIsNone(published["comparison"])
        self.assertFalse(published["seasonal"])
        self.assertEqual(published["routes"]["avoid"]["legal"], False)
        speeds = {item["way"]: item["laneSpeed"] for item in published["network"]["examples"]}
        self.assertEqual(speeds["29235087"], "16.67")
        self.assertEqual(speeds["100089298"], "27.78")
        self.assertEqual(published["network"]["artigasEntry"][0]["dir"], "r")
        self.assertEqual(published["network"]["artigasEntry"][0]["state"], "m")
        self.assertGreater(published["network"]["ringEdgesShorterThanOneMeter"], 0)
        self.assertTrue(all(item["type"] == "static" for item in published["network"]["signalPrograms"]))
        self.assertIn("1167219966", published["network"]["signalsWithoutProgram"])
        self.assertFalse((STAGE / "routes.rou.xml").exists())
        self.assertFalse((STAGE / "trips.xml").exists())
        self.assertFalse((STAGE / "trajectories.xml").exists())
        net = (STAGE / "red.net.xml").read_text(encoding="utf-8")
        self.assertIn("100089298#0", net)
        self.assertNotIn("252069937", net)
        self.assertNotIn("101195613", net)
        clip_ways = {way.get("id") for way in ET.parse(STAGE / "recorte.osm.xml").findall("way")}
        clip_nodes = {node.get("id") for node in ET.parse(STAGE / "recorte.osm.xml").findall("node")}
        verified_ways = {way.get("id") for way in ET.parse(STAGE / "red-verificada.osm.xml").findall("way")}
        self.assertIn("100089298", clip_ways)
        self.assertIn("252069937", clip_ways)
        self.assertNotIn("252069937", verified_ways)
        self.assertNotIn("101195613", verified_ways)
        for way_id in EXCLUDED:
            self.assertNotIn(way_id, clip_ways)
        self.assertNotIn("1156780611", clip_nodes)
        labels = {feature["properties"].get("label") for feature in json.loads(GEOJSON.read_text(encoding="utf-8"))["features"]}
        self.assertTrue({"Rotonda", "Parada 5", "Roosevelt", "Artigas", "Francia", "Pedragosa", "Avenida del Mar"} <= labels)

    def test_certified_replay_and_snapshot_stay(self):
        self.assertEqual(digest(REPLAY), REPLAY_SHA256)
        self.assertEqual(REPLAY.stat().st_size, 1084990)
        self.assertEqual(digest(SNAPSHOT), SNAPSHOT_SHA256)
        reference = json.loads((STAGE / "snapshot.ref.json").read_text(encoding="utf-8"))
        self.assertEqual(reference["sha256"], SNAPSHOT_SHA256)
        self.assertNotIn("maldonado.osm.gz", {path.name for path in STAGE.iterdir()})
