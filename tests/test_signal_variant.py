"""Experimental signal drafts stay outside the published runs."""

from functools import partial
from http.client import HTTPConnection
import hashlib
import json
from pathlib import Path
import threading
import unittest
import xml.etree.ElementTree as ET

import abrir_urbanflow
from src.study_server import StudyHandler
import sumo_scenario.signal_variant as variants
from sumo_scenario.signal_variant import SignalVariantError


PROJECT = Path(__file__).resolve().parents[1]
HONDURAS = PROJECT / "results/studies/298c6613a70a42ea926f6c46931bbf9a"
SECTOR = PROJECT / "results/etapa1c5-sector01/candidata/01c5b202611140000000000000000001"
HONDURAS_ID = "298c6613a70a42ea926f6c46931bbf9a"
SECTOR_ID = "01c5b202611140000000000000000001"
HONDURAS_CONTROLLER = "cluster_1360014840_13966777057_13966777058_2375592994"
SECTOR_CONTROLLER = "1155355178"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def phase_attribute(directory, controller, index, field):
    logic = next(item for item in ET.parse(directory / "network.net.xml").iter("tlLogic") if item.get("id") == controller)
    return logic.findall("phase")[index].get(field)


class SignalVariantTests(unittest.TestCase):
    def setUp(self):
        self.storage = PROJECT / "results" / "_tmp" / "ux4b1" / "variants"
        if self.storage.exists():
            for child in self.storage.glob("*.json"):
                child.unlink()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.previous = variants.VARIANTS
        variants.VARIANTS = self.storage
        self.hashes = {path: digest(path) for path in (
            HONDURAS / "network.net.xml", HONDURAS / "routes.rou.xml", HONDURAS / "replay.json",
            SECTOR / "network.net.xml", SECTOR / "routes.rou.xml", SECTOR / "replay.json",
        )}

    def tearDown(self):
        variants.VARIANTS = self.previous

    def test_reads_sumo_phases_and_blocks_a_controller_without_logic(self):
        program = variants.read_program(HONDURAS, HONDURAS_CONTROLLER)
        self.assertTrue(program["editable"])
        self.assertEqual(program["provenance"], None)
        self.assertEqual(program["provenanceLabel"], "Desconocida")
        self.assertEqual(program["program"]["type"], "static")
        self.assertEqual(program["program"]["programID"], "0")
        self.assertEqual(program["program"]["source"], "network.net.xml")
        self.assertEqual(program["program"]["phases"][0]["duration"], phase_attribute(HONDURAS, HONDURAS_CONTROLLER, 0, "duration"))
        self.assertEqual(len(program["program"]["phases"]), 9)
        self.assertNotIn("signal-states.xml", [item["file"] for item in program["sources"]])
        self.assertFalse((HONDURAS / "signals.add.xml").read_text(encoding="utf-8").find("<tlLogic") >= 0 and
                         any(item["file"] == "signals.add.xml" and item["definesProgram"] for item in program["sources"]))
        blocked = variants.read_program(HONDURAS, "sin-programa")
        self.assertFalse(blocked["editable"])
        self.assertIn("no tiene un tlLogic", blocked["reason"])
        self.assertIsNone(blocked["program"])
        with self.assertRaises(SignalVariantError):
            variants.create_variant(HONDURAS, "sin-programa")

    def test_actuated_program_exposes_only_its_own_times(self):
        program = variants.read_program(SECTOR, SECTOR_CONTROLLER)
        self.assertEqual(program["provenance"], "inferred")
        phase = program["program"]["phases"][0]
        self.assertEqual(phase["duration"], phase_attribute(SECTOR, SECTOR_CONTROLLER, 0, "duration"))
        self.assertEqual(phase["minDur"], phase_attribute(SECTOR, SECTOR_CONTROLLER, 0, "minDur"))
        self.assertEqual(phase["maxDur"], phase_attribute(SECTOR, SECTOR_CONTROLLER, 0, "maxDur"))
        self.assertNotIn("minDur", program["program"]["phases"][1])
        fields = {(item["phase"], item["field"]) for item in program["editableFields"]}
        self.assertIn((0, "minDur"), fields)
        self.assertNotIn((1, "minDur"), fields)

    def test_draft_edit_reset_and_reopen_leave_the_run_untouched(self):
        created = variants.create_variant(HONDURAS, HONDURAS_CONTROLLER)
        self.assertEqual(created["status"], "borrador experimental")
        self.assertNotEqual(created["baseDirectory"].split("/")[0], "src")
        proposed = json.loads(json.dumps(created["original"]))
        proposed["phases"][0]["duration"] = "25"
        saved = variants.update_variant(created["id"], proposed)
        self.assertEqual(saved["proposed"]["phases"][0]["duration"], "25")
        self.assertEqual(saved["original"]["phases"][0]["duration"], created["original"]["phases"][0]["duration"])
        self.assertEqual(saved["contract"]["comparisonEnabled"], False)
        self.assertFalse(saved["contract"]["simulate"])
        self.assertEqual(saved["contract"]["differences"], [
            {"phase": 0, "field": "duration", "original": created["original"]["phases"][0]["duration"], "proposed": "25"},
        ])
        reopened = variants.read_variant(created["id"])
        self.assertEqual(reopened["proposed"]["phases"][0]["duration"], "25")
        invalid = json.loads(json.dumps(created["original"]))
        invalid["phases"][0]["duration"] = "-1"
        with self.assertRaises(SignalVariantError):
            variants.update_variant(created["id"], invalid)
        invalid["phases"][0]["duration"] = created["original"]["phases"][0]["duration"]
        invalid["phases"][0]["state"] = "g"
        with self.assertRaises(SignalVariantError):
            variants.update_variant(created["id"], invalid)
        extra = json.loads(json.dumps(created["original"]))
        extra["phases"][0]["minDur"] = "5"
        with self.assertRaises(SignalVariantError):
            variants.update_variant(created["id"], extra)
        self.assertEqual(variants.read_variant(created["id"])["proposed"]["phases"][0]["duration"], "25")
        restored = variants.reset_variant(created["id"])
        self.assertEqual(restored["proposed"], restored["original"])
        another = variants.create_variant(HONDURAS, HONDURAS_CONTROLLER)
        self.assertNotEqual(another["id"], created["id"])
        self.assertEqual(sorted(self.storage.glob("*.json")).__len__(), 2)
        for path, expected in self.hashes.items():
            self.assertEqual(digest(path), expected, path.name)

    def test_actuated_bounds_follow_the_saved_phase(self):
        created = variants.create_variant(SECTOR, SECTOR_CONTROLLER)
        proposed = json.loads(json.dumps(created["original"]))
        proposed["phases"][0]["maxDur"] = "45"
        saved = variants.update_variant(created["id"], proposed)
        self.assertEqual(saved["proposed"]["phases"][0]["maxDur"], "45")
        proposed["phases"][0]["minDur"] = "80"
        proposed["phases"][0]["maxDur"] = created["original"]["phases"][0]["maxDur"]
        with self.assertRaises(SignalVariantError):
            variants.update_variant(created["id"], proposed)
        for path, expected in self.hashes.items():
            self.assertEqual(digest(path), expected, path.name)

    def test_http_reads_the_program_and_stores_the_draft_elsewhere(self):
        handler = partial(StudyHandler, directory=str(PROJECT / "urbanflow-web"))
        server = abrir_urbanflow.LocalServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        try:
            program = self.request(port, "GET", f"/api/studies/{HONDURAS_ID}/signal-program?controller={HONDURAS_CONTROLLER}")
            self.assertEqual(program["status"], 200)
            self.assertEqual(program["body"]["program"]["phases"][0]["duration"], "20")
            blocked = self.request(port, "GET", f"/api/studies/{HONDURAS_ID}/signal-program?controller=sin-programa")
            self.assertEqual(blocked["status"], 200)
            self.assertFalse(blocked["body"]["editable"])
            created = self.request(port, "POST", f"/api/studies/{HONDURAS_ID}/signal-variants", {"controllerId": HONDURAS_CONTROLLER})
            self.assertEqual(created["status"], 201)
            self.assertTrue(str(self.storage) in str(variants.VARIANTS))
            stored = self.storage / f"{created['body']['id']}.json"
            self.assertTrue(stored.is_file())
            self.assertFalse((HONDURAS / f"{created['body']['id']}.json").exists())
        finally:
            server.shutdown()
            server.server_close()

    def test_comparison_rules_remain_the_network_and_traffic_gates(self):
        comparison = (PROJECT / "sumo_scenario" / "study_comparison.py").read_text(encoding="utf-8")
        rerun = (PROJECT / "src" / "study_server.py").read_text(encoding="utf-8")
        self.assertIn("network_files[0].read_bytes() != network_files[1].read_bytes()", comparison)
        self.assertIn("ET.canonicalize", comparison)
        self.assertIn("traffic['counts']", rerun)
        created = variants.create_variant(HONDURAS, HONDURAS_CONTROLLER)
        self.assertFalse(created["contract"]["comparisonEnabled"])
        self.assertIn("start_rerun()", " ".join(created["contract"]["reasons"]))

    def request(self, port, method, path, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return {"status": response.status, "body": json.loads(raw) if raw else {}}
        finally:
            connection.close()


    def test_execution_rejects_an_unchanged_or_inferred_program(self):
        from sumo_scenario import signal_execution as execution

        created = variants.create_variant(HONDURAS, HONDURAS_CONTROLLER)
        with self.assertRaises(SignalVariantError) as empty:
            execution.begin_execution(created["id"])
        self.assertIn("no tiene cambios", str(empty.exception))
        self.assertEqual(variants.read_variant(created["id"])["status"], "borrador experimental")
        proposed = json.loads(json.dumps(created["original"]))
        proposed["phases"][0]["duration"] = "25"
        saved = variants.update_variant(created["id"], proposed)
        target = self.storage / "signal-variant.tll.xml"
        execution._write_program(target, HONDURAS_CONTROLLER, saved["proposed"])
        logic = ET.parse(target).getroot().find("tlLogic")
        self.assertEqual(logic.get("programID"), "experimental")
        self.assertEqual(logic.findall("phase")[0].get("duration"), "25")
        self.assertEqual(logic.findall("phase")[0].get("state"), created["original"]["phases"][0]["state"])
        self.assertEqual([phase.get("state") for phase in logic.findall("phase")],
                         [phase["state"] for phase in created["original"]["phases"]])
        execution.begin_execution(created["id"])
        try:
            with self.assertRaises(SignalVariantError) as duplicate:
                execution.begin_execution(created["id"])
            self.assertEqual(duplicate.exception.http_status, 409)
            self.assertIn(created["id"], execution.RUNNING)
        finally:
            execution.fail_execution(created["id"], "Prueba interrumpida.")
        self.assertNotIn(created["id"], execution.RUNNING)
        inferred = variants.create_variant(SECTOR, SECTOR_CONTROLLER)
        with self.assertRaises(SignalVariantError) as blocked:
            execution.begin_execution(inferred["id"])
        self.assertIn("inferido", str(blocked.exception))
        damaged = variants.read_variant(created["id"])
        damaged["integrity"]["network.net.xml"] = "0" * 64
        damaged["status"] = "borrador experimental"
        (self.storage / f"{created['id']}.json").write_text(json.dumps(damaged), encoding="utf-8")
        with self.assertRaises(SignalVariantError) as changed:
            execution.begin_execution(created["id"])
        self.assertIn("cambiaron", str(changed.exception))

    def test_interrupted_execution_becomes_an_error_without_a_second_run(self):
        from sumo_scenario import signal_execution as execution

        created = variants.create_variant(HONDURAS, HONDURAS_CONTROLLER)
        proposed = json.loads(json.dumps(created["original"]))
        proposed["phases"][0]["duration"] = "25"
        variants.update_variant(created["id"], proposed)
        execution.begin_execution(created["id"])
        execution.RUNNING.discard(created["id"])
        before = {path.name for path in execution.RUNS.glob("*")}
        with self.assertRaises(SignalVariantError) as interrupted:
            execution.begin_execution(created["id"])
        self.assertEqual(interrupted.exception.http_status, 409)
        self.assertIn("interrumpió", str(interrupted.exception))
        stored = variants.read_variant(created["id"])
        self.assertEqual(stored["status"], "error")
        self.assertFalse(stored["execution"]["resultsValid"])
        self.assertFalse(stored["execution"]["comparison"]["available"])
        self.assertNotIn(created["id"], execution.RUNNING)
        self.assertEqual({path.name for path in execution.RUNS.glob("*")}, before)
        stored["status"] = "finalizado"
        stored["execution"] = {"resultsValid": True, "comparison": {"available": True}}
        path = self.storage / f"{created['id']}.json"
        path.write_text(json.dumps(stored), encoding="utf-8")
        signature = path.read_bytes()
        recovered = execution.recover_interrupted(created["id"])
        self.assertEqual(recovered["status"], "finalizado")
        self.assertEqual(path.read_bytes(), signature)
        with self.assertRaises(SignalVariantError) as repeated:
            execution.begin_execution(created["id"])
        self.assertEqual(repeated.exception.http_status, 409)
        self.assertIn("ya fue ejecutada", str(repeated.exception))

    def test_http_blocks_execution_without_a_static_program(self):
        handler = partial(StudyHandler, directory=str(PROJECT / "urbanflow-web"))
        server = abrir_urbanflow.LocalServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        try:
            created = self.request(port, "POST", f"/api/studies/{SECTOR_ID}/signal-variants", {"controllerId": SECTOR_CONTROLLER})
            self.assertEqual(created["status"], 201)
            refused = self.request(port, "POST", f"/api/signal-variants/{created['body']['id']}/execute", {})
            self.assertEqual(refused["status"], 422)
            self.assertIn("inferido", refused["body"]["message"])
            self.assertEqual(variants.read_variant(created["body"]["id"])["status"], "borrador experimental")
        finally:
            server.shutdown()
            server.server_close()


class SignalExecutionPilot(unittest.TestCase):
    def test_honduras_control_and_variant_come_from_sumo(self):
        from sumo_scenario import signal_execution as execution

        before = {path.relative_to(HONDURAS).as_posix(): digest(path) for path in HONDURAS.rglob("*") if path.is_file()}
        created = variants.create_variant(HONDURAS, HONDURAS_CONTROLLER)
        proposed = json.loads(json.dumps(created["original"]))
        proposed["phases"][0]["duration"] = "25"
        variants.update_variant(created["id"], proposed)
        execution.begin_execution(created["id"])
        finished = execution.run_execution(created["id"])
        self.assertIsNotNone(finished)
        self.assertEqual(finished["status"], "finalizado")
        self.assertTrue(finished["execution"]["resultsValid"])
        self.assertTrue(finished["execution"]["programActive"])
        self.assertEqual(finished["execution"]["evidence"]["variantPhaseSeconds"][0], 25)
        self.assertEqual(finished["execution"]["evidence"]["controlPhaseSeconds"][0], 20)
        self.assertEqual(finished["execution"]["loadedProgramID"], "experimental")
        self.assertTrue(finished["execution"]["comparison"]["available"])
        self.assertFalse(finished["contract"]["comparisonEnabled"])
        self.assertFalse(finished["contract"]["simulate"])
        indicators = finished["execution"]["comparison"]["indicators"]
        self.assertIn("completed", indicators)
        self.assertIsNotNone(indicators["meanTravelSeconds"]["control"])
        self.assertIsNotNone(indicators["meanTravelSeconds"]["variant"])
        with self.assertRaises(SignalVariantError) as duplicate:
            execution.begin_execution(created["id"])
        self.assertEqual(duplicate.exception.http_status, 409)
        after = {path.relative_to(HONDURAS).as_posix(): digest(path) for path in HONDURAS.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        variant_run = PROJECT / finished["execution"]["variantRun"]["directory"]
        control_run = PROJECT / finished["execution"]["control"]["directory"]
        self.assertNotEqual(variant_run, HONDURAS)
        self.assertEqual(digest(variant_run / "network.net.xml"), before["network.net.xml"])
        self.assertEqual(digest(control_run / "routes.rou.xml"), before["routes.rou.xml"])
        program = ET.parse(variant_run / "signal-variant.tll.xml").getroot().find("tlLogic")
        self.assertEqual(program.get("programID"), "experimental")
        self.assertFalse((control_run / "signal-variant.tll.xml").exists())
        replay = execution.read_experimental_replay(created["id"], "variant")
        self.assertTrue(replay["experimental"])
        self.assertEqual(replay["experimentalRole"], "variant")
        self.assertGreater(len(replay["frames"]), 2)


if __name__ == "__main__":
    unittest.main()
