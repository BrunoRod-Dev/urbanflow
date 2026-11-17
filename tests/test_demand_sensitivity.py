"""La demanda sintética escala los 15 flujos y no toca la corrida guardada."""

from hashlib import sha256
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

import tools.demand_sensitivity as demand
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


class DemandScaleTest(unittest.TestCase):
    def test_scale_keeps_routes_and_only_changes_the_count(self):
        source = demand.SOURCE / "routes.rou.xml"
        original = source.read_bytes()
        doubled = demand.scale_routes(source, 6)
        tripled = demand.scale_routes(source, 9)
        self.assertEqual(demand.scale_routes(source, 3), original)
        self.assertEqual(len(doubled), len(original))
        self.assertEqual(doubled.count(b'number="6"'), 15)
        self.assertEqual(tripled.count(b'number="9"'), 15)
        flows = list(ET.fromstring(doubled).findall("flow"))
        original_flows = list(ET.fromstring(original).findall("flow"))
        self.assertEqual([flow.get("id") for flow in flows], [flow.get("id") for flow in original_flows])
        self.assertEqual([flow.get("begin") for flow in flows], [flow.get("begin") for flow in original_flows])
        self.assertEqual([flow.get("route") for flow in flows], [flow.get("route") for flow in original_flows])
        self.assertTrue(all(flow.get("end") == "240" for flow in flows))

    def test_open_phase_at_the_horizon_is_not_a_finished_green(self):
        path = ROOT / "results/_tmp/etapa1f2/phase-sample.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "<tlsStates>"
            "<tlsState time='0' id='c' phase='0'/>"
            "<tlsState time='15' id='c' phase='1'/>"
            "<tlsState time='21' id='c' phase='0'/>"
            "</tlsStates>",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink)
        lengths, censored = demand.closed_phases(path, "c", 240)
        self.assertEqual(lengths["0"], [15.0])
        self.assertEqual(censored, {"phase": "0", "seconds": 219.0})
        effect = demand.cap_effect(lengths, {"0": [15.0]}, censored)
        self.assertEqual(effect["cutByCap"], 0)
        self.assertEqual(effect["censoredPhase0"], 219.0)

    def test_cohort_excludes_vehicles_still_running_at_the_horizon(self):
        path = ROOT / "results/_tmp/etapa1f2/cohort-sample.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "<tripinfos>"
            "<tripinfo id='early' depart='0' arrival='40' duration='40' waitingTime='2' vaporized=''/>"
            "<tripinfo id='late' depart='160' arrival='-1' duration='80' waitingTime='30' vaporized='end'/>"
            "<tripinfo id='held' depart='-1' arrival='-1' duration='0' waitingTime='0' vaporized=''/>"
            "</tripinfos>",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink)
        finished, pending, rejected = demand.classify_trips(path)
        self.assertEqual(list(finished), ["early"])
        self.assertEqual(list(pending), ["late"])
        self.assertEqual(rejected, [])
        other = {"early": (50.0, 4.0, 0.0), "late": (70.0, 10.0, 160.0)}
        same = demand.cohort(finished, other)
        self.assertEqual(same["count"], 1)
        self.assertEqual(same["meanTravel"]["absolute"], 10)
        self.assertNotIn("late", same)

    def test_published_levels_match_sumo_and_leave_the_saved_run_alone(self):
        report = json.loads((ROOT / "urbanflow-web/assets/decision-demand.json").read_text(encoding="utf-8"))
        self.assertTrue(report["experimental"])
        self.assertFalse(report["calibrated"])
        self.assertFalse(report["seasonal"])
        self.assertEqual([level["demand"] for level in report["levels"]], [45, 90, 135])
        self.assertIn("Intendencia", report["conclusion"])
        self.assertIn("temporada", report["conclusion"])
        for level in report["levels"]:
            evidence = level["evidence"]
            recomputed = demand.level_report(
                level["demand"],
                ROOT / evidence["tripsA"], ROOT / evidence["tripsB"],
                ROOT / evidence["signalsA"], ROOT / evidence["signalsB"],
                ROOT / evidence["routes"],
            )
            self.assertEqual(level["completed"], recomputed["completed"])
            self.assertEqual(level["unfinished"], recomputed["unfinished"])
            self.assertEqual(level["cohort"], recomputed["cohort"])
            self.assertEqual(level["cap"], recomputed["cap"])
            self.assertEqual(level["horizonLimited"], recomputed["horizonLimited"])
            self.assertEqual(digest(ROOT / evidence["routes"]), evidence["routesSha256"])
            self.assertLessEqual(level["cap"]["maxB"], 15.5)
        base = report["levels"][0]
        self.assertEqual(
            decision.completed_signature(demand.SOURCE / "trips.xml"),
            decision.completed_signature(ROOT / base["evidence"]["tripsA"]),
        )
        self.assertTrue(demand.only_maxdur_edit(
            demand.SOURCE / "network.net.xml", ROOT / report["network"]))
        for name, expected in decision.source_hashes().items():
            self.assertEqual(digest(demand.SOURCE / name), expected)
        self.assertEqual(digest(REPLAY), REPLAY_SHA256)
        self.assertEqual(REPLAY.stat().st_size, 1084990)
