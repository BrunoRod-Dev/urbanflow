"""La comparación experimental reproduce la corrida guardada y no la modifica."""

from hashlib import sha256
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

import tools.decision_ab as decision


ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "results/etapa1c5-sector01/candidata/01c5b202611140000000000000000001/replay.json"
REPLAY_SHA256 = "03b534e910cd373360eb595fa463dff5e7ee9f743368b67378c7e6aca141080b"


def digest(path):
    hashed = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


class DecisionComparisonTest(unittest.TestCase):
    def test_mean_uses_only_finished_trips(self):
        path = ROOT / "results/_tmp/etapa1f1/metric-sample.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "<tripinfos>"
            "<tripinfo id='a' arrival='10' duration='10' waitingTime='1'/>"
            "<tripinfo id='b' arrival='-1' duration='5' waitingTime='4'/>"
            "</tripinfos>",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink)
        measured = decision.measure_trips(path)
        self.assertEqual(measured["inserted"], 2)
        self.assertEqual(measured["completed"], 1)
        self.assertEqual(measured["meanTravel"], 10)
        self.assertEqual(measured["meanWait"], 1)
        self.assertEqual(decision.metric_pair(10, 15, None), {"a": 10, "b": 15, "absolute": 5, "percent": 50})
        self.assertIsNone(decision.metric_pair(0, 2, None)["percent"])

    def test_phase_samples_merge_until_the_phase_changes(self):
        path = ROOT / "results/_tmp/etapa1f1/phase-sample.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "<tlsStates>"
            "<tlsState time='0' id='c' phase='0'/>"
            "<tlsState time='0.5' id='c' phase='0'/>"
            "<tlsState time='1.0' id='other' phase='0'/>"
            "<tlsState time='13' id='c' phase='1'/>"
            "</tlsStates>",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink)
        lengths = decision.phase_lengths(path, "c", 20)
        self.assertEqual(lengths["0"], [13.0])
        self.assertEqual(lengths["1"], [7.0])

    def test_published_result_matches_sumo_and_leaves_sources_untouched(self):
        report = json.loads((ROOT / "urbanflow-web/assets/decision-roosevelt.json").read_text(encoding="utf-8"))
        stage = ROOT / "results/_tmp/etapa1f1"
        self.assertTrue(report["experimental"])
        self.assertFalse(report["calibrated"])
        self.assertFalse(report["queues"]["measured"])
        self.assertIn("Intendencia", report["notice"])
        for name, expected in report["sources"]["sha256"].items():
            self.assertEqual(digest(decision.SOURCE / name), expected)
        self.assertEqual(decision.completed_signature(decision.SOURCE / "trips.xml"),
                         decision.completed_signature(stage / "a/trips.xml"))
        self.assertTrue(decision.only_maxdur_edit(decision.SOURCE / "network.net.xml", stage / "b-network.net.xml"))
        for key in ("meanTravel", "meanWait", "completed", "inserted"):
            measured = {side: decision.measure_trips(stage / side / "trips.xml") for side in ("a", "b")}
            field = {"meanTravel": "meanTravel", "meanWait": "meanWait", "completed": "completed", "inserted": "inserted"}[key]
            digits = None if key in {"completed", "inserted"} else 2
            self.assertEqual(report["metrics"][key], {
                "label": report["metrics"][key]["label"],
                "unit": report["metrics"][key]["unit"],
                "decimals": report["metrics"][key]["decimals"],
                **decision.metric_pair(measured["a"][field], measured["b"][field], digits),
            })
        for side in ("a", "b"):
            lengths = decision.phase_lengths(stage / side / "signal-states.xml", decision.CONTROLLER, decision.END)
            self.assertEqual(report["phase0MaxSeconds"][side], round(max(lengths.get("0", [0])), 1))
        self.assertEqual(report["phase0MaxSeconds"], {"a": 17.0, "b": 15.0})
        paired = decision.paired_trips(stage / "a/trips.xml", stage / "b/trips.xml")
        self.assertEqual(report["metrics"]["meanTravelSame"]["a"], round(paired["meanTravel"][0], 2))
        self.assertEqual(report["metrics"]["meanTravelSame"]["b"], round(paired["meanTravel"][1], 2))
        self.assertIn("no produce una diferencia relevante", report["limitation"])
        self.assertEqual(digest(REPLAY), REPLAY_SHA256)
        self.assertEqual(REPLAY.stat().st_size, 1084990)
        self.assertFalse((decision.SOURCE / "b-network.net.xml").exists())

    def test_reference_phase_is_the_actuated_program(self):
        logic = next(item for item in ET.parse(decision.SOURCE / "network.net.xml").iter("tlLogic")
                     if item.get("id") == decision.CONTROLLER)
        phase = logic.findall("phase")[0]
        self.assertEqual(logic.get("type"), "actuated")
        self.assertEqual(phase.get("duration"), "39")
        self.assertEqual(phase.get("maxDur"), "50")
        self.assertEqual(phase.get("state"), decision.PHASE_STATE)
