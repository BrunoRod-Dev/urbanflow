"""Contrato de los manifiestos de sector, sin regenerar la candidata."""

from hashlib import sha256
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "urbanflow-web"
CANDIDATE = ROOT / "results/etapa1c5-sector01/candidata"
REPLAY = CANDIDATE / "01c5b202611140000000000000000001/replay.json"
REPLAY_SHA256 = "03b534e910cd373360eb595fa463dff5e7ee9f743368b67378c7e6aca141080b"


def digest(path):
    hashed = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


class SectorManifestTest(unittest.TestCase):
    def test_certified_replay_keeps_its_hash(self):
        self.assertEqual(digest(REPLAY), REPLAY_SHA256)
        self.assertEqual(REPLAY.stat().st_size, 1084990)

    def test_sector01_lists_the_network_controllers_as_inferred(self):
        sector = json.loads((WEB / "sectors/sector01.json").read_text(encoding="utf-8"))
        network = CANDIDATE / "01c5b202611140000000000000000001/network.net.xml"
        controllers = {item.get("id") for item in ET.parse(network).iter("tlLogic")}
        declared = {item["id"] for item in sector["signals"]}
        self.assertEqual(declared, controllers)
        self.assertTrue(all(item["program"] == "inferred" for item in sector["signals"]))
        self.assertFalse(any(item.get("camera") for item in sector["signals"]))
        self.assertFalse(sector["data"]["fieldValidated"])
        self.assertEqual(digest(ROOT / sector["data"]["geography"]), sector["data"]["geographySha256"])
        self.assertEqual(digest(ROOT / sector["data"]["osmExtract"]), sector["data"]["osmExtractSha256"])

    def test_declared_assets_stay_in_place(self):
        roosevelt = json.loads((WEB / "sectors/roosevelt-camacho.json").read_text(encoding="utf-8"))
        for key in ("buildings", "curbSurvey", "schematic"):
            self.assertTrue((ROOT / roosevelt["data"][key]).is_file(), key)
        sector = json.loads((WEB / "sectors/sector01.json").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / sector["data"]["candidate"]).is_dir())
        self.assertFalse((CANDIDATE / "sectors").exists())
