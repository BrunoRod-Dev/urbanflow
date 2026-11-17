"""La candidata 1C.5 y el pipeline versionable no pueden dar PASS sin sus archivos."""

from hashlib import sha256
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "results/etapa1c5-sector01/candidata"
REPLAY_ID = "01c5b202611140000000000000000001"
PLAYER_FILES = (
    "manifest.json",
    "sector01.geojson",
    f"{REPLAY_ID}/replay.json",
    f"{REPLAY_ID}/recorte.osm.xml",
    f"{REPLAY_ID}/network.net.xml",
)
NETCONVERT_FLAGS = (
    "--osm-files", "recorte.osm.xml", "--keep-edges.in-geo-boundary",
    "--keep-edges.by-vclass", "passenger,bus", "--osm.turn-lanes", "true",
    "--geometry.remove", "true", "--tls.guess-signals", "true", "--tls.join", "true",
    "--tls.join-dist", "30", "--tls.default-type", "actuated", "--no-turnarounds", "true",
    "--roundabouts.guess", "true", "--output.street-names", "true",
    "--output.original-names", "true", "--output-file", "network.net.xml",
    "--plain-output-prefix", "map", "--proj.plain-geo", "true", "--plain-output.lanes", "true",
    "--precision.geo", "7", "--aggregate-warnings", "-1",
)
SUMO_SETTINGS = (
    "'end': '540'", "'step-length': '0.5'", "'time-to-teleport': '-1'", "'seed': '42'",
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class Sector01Pipeline(unittest.TestCase):
    def test_reproduction_tools_do_not_import_results_code(self):
        files = sorted((ROOT / "tools").glob("*.py")) + [ROOT / "probar_sector01.py"]
        offenders = []
        for file in files:
            text = file.read_text(encoding="utf-8")
            if "spec_from_file_location" in text or "exec_module" in text:
                offenders.append(f"{file.name}: carga un archivo externo")
            if re.search(r"sys\.path\.(insert|append)\([^)\n]*results", text):
                offenders.append(f"{file.name}: agrega results al path de importación")
            if re.search(r"^\s*(?:import|from)\s+probar\b", text, re.M):
                offenders.append(f"{file.name}: importa probar desde el directorio de resultados")
        self.assertEqual(offenders, [])

        manifest = ROOT / "results/etapa1c-sector01-validacion/manifest.json"
        self.assertTrue(manifest.is_file(), "Falta el manifiesto histórico necesario para cargar el pipeline.")
        import tools.sector01_candidato
        import tools.sector01_cerrar
        import tools.sector01_probar
        import tools.sector01_reproducir
        results = (ROOT / "results").resolve()
        loaded = []
        for name, module in list(__import__("sys").modules.items()):
            origin = getattr(module, "__file__", None)
            if origin and Path(origin).resolve().is_relative_to(results):
                loaded.append(name)
        self.assertEqual(loaded, [])
        for module in (tools.sector01_candidato, tools.sector01_cerrar,
                       tools.sector01_probar, tools.sector01_reproducir):
            self.assertTrue(Path(module.__file__).resolve().is_relative_to((ROOT / "tools").resolve()))

    def test_new_manifest_paths_are_relative_and_old_ones_still_resolve(self):
        validation = ROOT / "results/etapa1c-sector01-validacion/manifest.json"
        self.assertTrue(validation.is_file(), "Falta el manifiesto histórico de la validación.")
        from tools.sector01_probar import MANIFEST, recorded_file
        from tools.sector01_reproducir import project_relative
        for name, tool in MANIFEST["tools"].items():
            binary = recorded_file(tool["path"])
            self.assertTrue(binary.is_file(), name)
            self.assertEqual(digest(binary), tool["sha256"], name)
            self.assertFalse(Path(project_relative(binary)).is_absolute(), name)
        snapshot = recorded_file(MANIFEST["snapshot"]["path"])
        self.assertEqual(digest(snapshot), MANIFEST["snapshot"]["sha256"])
        self.assertEqual(project_relative(snapshot), "sumo_scenario/regional/maldonado.osm.gz")
        fixture = "tests/fixtures/historicos_93.json"
        absolute = "C:/otra/maquina/urbanflow-main/" + fixture
        self.assertEqual(recorded_file(fixture).resolve(), (ROOT / fixture).resolve())
        self.assertEqual(recorded_file(absolute).resolve(), (ROOT / fixture).resolve())

    def test_candidate_1c5_and_player_files_match_recorded_hashes(self):
        manifest_path = CANDIDATE / "manifest.json"
        self.assertTrue(manifest_path.is_file(), "Falta la candidata certificada de 1C.5.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["replayId"], REPLAY_ID)
        self.assertFalse(manifest["fieldValidated"])
        self.assertFalse(manifest["sumoRerun"])
        self.assertEqual(len(manifest["artifacts"]), 16)
        self.assertEqual(len(manifest["sourceFiles"]), 11)
        for relative in PLAYER_FILES:
            self.assertTrue((CANDIDATE / relative).is_file(), relative)
        for relative, expected in manifest["artifacts"].items():
            file = CANDIDATE / relative
            self.assertTrue(file.is_file(), relative)
            self.assertEqual(digest(file), expected, relative)
        for relative, expected in manifest["sourceFiles"].items():
            file = ROOT / relative
            self.assertTrue(file.is_file(), relative)
            self.assertEqual(digest(file), expected, relative)
        events_path = ROOT / "results/etapa1c5-sector01/qa/qa-events.json"
        self.assertTrue(events_path.is_file(), "Faltan las alertas de QA de la candidata.")
        events = json.loads(events_path.read_text(encoding="utf-8"))
        self.assertEqual(events["studyId"], REPLAY_ID)
        for name, expected in events["sourceHashes"].items():
            file = CANDIDATE / REPLAY_ID / name
            self.assertTrue(file.is_file(), name)
            self.assertEqual(digest(file), expected, name)

    def test_historical_hashes_fail_when_a_file_is_missing(self):
        manifest = json.loads((ROOT / "tests/fixtures/historicos_93.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["count"], 93)
        self.assertEqual(len(manifest["files"]), 93)
        for item in manifest["files"]:
            file = ROOT / item["path"]
            self.assertTrue(file.is_file(), item["path"])
            self.assertEqual(digest(file), item["sha256"], item["path"])

    def test_certified_sumo_parameters_remain(self):
        source = (ROOT / "tools/sector01_reproducir.py").read_text(encoding="utf-8")
        compile_network = source.split("def compile_network", 1)[1].split("\ndef ", 1)[0]
        simulation = source.split("def run_simulation", 1)[1].split("\ndef ", 1)[0]
        for flag in NETCONVERT_FLAGS:
            self.assertIn(flag, compile_network)
        for setting in SUMO_SETTINGS:
            self.assertIn(setting, simulation)


if __name__ == "__main__":
    unittest.main()
