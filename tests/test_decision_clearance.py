"""El despeje alarga la simulación y no cambia la demanda ni la red guardada."""

from hashlib import sha256
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

import tools.decision_ab as decision
import tools.decision_clearance as clearance


ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "results/etapa1c5-sector01/candidata/01c5b202611140000000000000000001/replay.json"
REPLAY_SHA256 = "03b534e910cd373360eb595fa463dff5e7ee9f743368b67378c7e6aca141080b"
SAMPLE = (
    "<tripinfos>"
    "<tripinfo id='done' depart='0' arrival='100' duration='100' waitingTime='1' vaporized=''/>"
    "<tripinfo id='later' depart='200' arrival='400' duration='200' waitingTime='20' vaporized=''/>"
    "<tripinfo id='stuck' depart='180' arrival='-1' duration='1020' waitingTime='400' vaporized='end'/>"
    "<tripinfo id='late' depart='250' arrival='500' duration='250' waitingTime='5' vaporized=''/>"
    "<tripinfo id='held' depart='-1' arrival='-1' duration='0' waitingTime='0' vaporized=''/>"
    "</tripinfos>"
)


def digest(path):
    hashed = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


class ClearanceMethodTest(unittest.TestCase):
    def test_window_counts_keep_late_and_unfinished_out_of_the_mean(self):
        path = ROOT / "results/_tmp/etapa1f3/window-sample.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SAMPLE, encoding="utf-8")
        self.addCleanup(path.unlink)
        rows, rejected = clearance.read_trips(path)
        self.assertEqual(rejected, [])
        counts = clearance.partition(rows)
        self.assertEqual(counts["completedAtGeneration"], 1)
        self.assertEqual(counts["pendingAtGeneration"], 2)
        self.assertEqual(counts["enteredAfterGeneration"], 1)
        self.assertEqual(counts["notEntered"], 1)
        self.assertEqual(counts["stillUnfinished"], 1)
        self.assertIsNone(counts["clearanceSeconds"])
        other = {
            "done": (90.0, 2.0, 0.0),
            "later": (180.0, 10.0, 200.0),
            "late": (240.0, 4.0, 250.0),
            "stuck": (50.0, 1.0, 180.0),
        }
        same = clearance.cohort(
            clearance.within_generation(counts["finished"]),
            clearance.within_generation(other),
        )
        self.assertEqual(same["count"], 2)
        self.assertEqual(sorted(set(counts["finished"]) & set(other) - {"late"}), ["done", "later"])

    def test_clearance_is_the_last_arrival_only_when_everyone_finishes(self):
        rows, _ = clearance.read_trips(self._written("clear-sample.xml", (
            "<tripinfos>"
            "<tripinfo id='a' depart='0' arrival='100.50' duration='100.50' waitingTime='0' vaporized=''/>"
            "<tripinfo id='b' depart='240' arrival='360' duration='120' waitingTime='3' vaporized=''/>"
            "</tripinfos>"
        )))
        self.assertEqual(clearance.partition(rows)["clearanceSeconds"], 360.0)
        self.assertEqual(clearance.partition(rows)["pendingAtGeneration"], 1)

    def test_detector_warning_names_the_internal_movements(self):
        network = clearance.SOURCE / "network.net.xml"
        before = digest(network)
        indexes = clearance.warned_indexes(
            "Warning: At actuated tlLogic "
            f"'{clearance.CONTROLLER}', linkIndex 3,4,8,9,10,11,12,21 has no controlling detector.",
            clearance.CONTROLLER,
        )
        self.assertEqual(indexes, (3, 4, 8, 9, 10, 11, 12, 21))
        movements = {item["linkIndex"]: item for item in clearance.link_movements(network, clearance.CONTROLLER)}
        self.assertEqual(movements[3]["fromName"], "Honduras")
        self.assertEqual(movements[3]["toName"], "Zelmar Michelini")
        self.assertEqual(movements[3]["laneLength"], 0.1)
        self.assertFalse(movements[3]["greenInCappedPhase"])
        self.assertEqual(movements[4]["direction"], "a la izquierda")
        self.assertTrue(movements[8]["greenInCappedPhase"])
        self.assertTrue(movements[9]["greenInCappedPhase"])
        self.assertEqual(movements[10]["fromName"], "Honduras")
        self.assertLess(movements[10]["laneLength"], 5)
        self.assertFalse(movements[12]["greenInCappedPhase"])
        self.assertTrue(movements[21]["greenInCappedPhase"])
        self.assertEqual(movements[21]["toName"], "Honduras")
        self.assertEqual(digest(network), before)

    def test_published_clearance_matches_sumo_and_leaves_the_saved_run_alone(self):
        report = json.loads((ROOT / "urbanflow-web/assets/decision-clearance.json").read_text(encoding="utf-8"))
        self.assertTrue(report["experimental"])
        self.assertFalse(report["calibrated"])
        self.assertFalse(report["seasonal"])
        self.assertEqual(report["detector"]["linkIndexes"], [3, 4, 8, 9, 10, 11, 12, 21])
        self.assertEqual(report["detector"]["cappedPhaseWithoutDetector"], [8, 9, 21])
        self.assertTrue(report["detector"]["conditionsInterpretation"])
        self.assertIn("Intendencia", report["conclusion"])
        self.assertIn("sintética", report["conclusion"])
        self.assertIn(clearance.CONTROLLER, report["detector"]["interpretation"])
        self.assertEqual([level["demand"] for level in report["levels"]], [45, 90, 135])
        for level in report["levels"]:
            evidence = level["evidence"]
            prior_a, prior_b = clearance.PRIOR_TRIPS[level["demand"]]
            recomputed = clearance.level_report(
                level["demand"],
                ROOT / evidence["tripsA"], ROOT / evidence["tripsB"],
                ROOT / evidence["routes"], prior_a, prior_b,
            )
            self.assertEqual(level["completedAtGeneration"], recomputed["completedAtGeneration"])
            self.assertEqual(level["pendingAtGeneration"], recomputed["pendingAtGeneration"])
            self.assertEqual(level["clearanceSeconds"], recomputed["clearanceSeconds"])
            self.assertEqual(level["stillUnfinished"], recomputed["stillUnfinished"])
            self.assertEqual(level["enteredAfterGeneration"], recomputed["enteredAfterGeneration"])
            self.assertEqual(level["cohort"], recomputed["cohort"])
            self.assertEqual(level["medianTravelChange"], recomputed["medianTravelChange"])
            self.assertEqual(level["travelShape"], recomputed["travelShape"])
            self.assertTrue(level["horizonAgrees"])
            self.assertEqual(digest(ROOT / evidence["routes"]), evidence["routesSha256"])
            flows = list(ET.parse(ROOT / evidence["routes"]).iter("flow"))
            self.assertTrue(all(flow.get("end") == "240" for flow in flows))
            self.assertFalse((ROOT / evidence["tripsA"]).with_name("signal-states.xml").exists())
            self.assertFalse((ROOT / evidence["tripsB"]).with_name("signal-states.xml").exists())
            for log_name in ("logA", "logB"):
                self.assertEqual(
                    clearance.warned_indexes((ROOT / evidence[log_name]).read_text(encoding="utf-8"), clearance.CONTROLLER),
                    tuple(report["detector"]["linkIndexes"]),
                )
        self.assertTrue(clearance.only_maxdur_edit(
            clearance.SOURCE / "network.net.xml", ROOT / report["network"]))
        for name, expected in decision.source_hashes().items():
            self.assertEqual(digest(clearance.SOURCE / name), expected)
        self.assertEqual(digest(REPLAY), REPLAY_SHA256)
        self.assertEqual(REPLAY.stat().st_size, 1084990)

    def _written(self, name, text):
        path = ROOT / "results/_tmp/etapa1f3" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.addCleanup(path.unlink)
        return path
