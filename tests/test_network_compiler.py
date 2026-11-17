"""Tests for the optional frozen network entry point, without SUMO by default."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from sumo_scenario.compound_crossings import CROSSINGS, joined_id
from sumo_scenario.network_compiler import PackageError, compile_package
from sumo_scenario.study import StudyError


NETWORK = b'<net><location/><edge id="a" from="x" to="y"><lane id="a_0"/></edge></net>'


class NetworkCompilerTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = self.root / 'source'
        self.package.mkdir()
        self.source = self.package / 'original.net.xml'
        self.source.write_bytes(NETWORK)
        self.manifest_path = self.package / 'manifest.json'
        self.output = self.root / 'output'
        self.manifest = {'schemaVersion': 1, 'packageId': 'fixture', 'revision': '1', 'stage': 'final',
                         'applied': ['geometry-adjustment', 'compound-crossings'], 'pending': [],
                         'artifacts': {'network.net.xml': {'path': self.source.name,
                                                          'sha256': sha256(NETWORK).hexdigest()}}}

    def compile(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding='utf-8')
        return compile_package(self.manifest_path, self.output)

    def assert_rejected(self, message):
        with self.assertRaisesRegex(PackageError, message):
            self.compile()
        self.assertFalse(self.output.exists())

    def test_final_is_copied_without_tool_discovery_or_rebuild(self):
        with patch('sumo_scenario.network_compiler.sumo_tools') as locate, \
                patch('sumo_scenario.network_compiler.rebuild_crossings') as rebuild:
            result = self.compile()
        self.assertEqual(result.read_bytes(), NETWORK)
        self.assertEqual(self.source.read_bytes(), NETWORK)
        locate.assert_not_called()
        rebuild.assert_not_called()
        receipt = json.loads((self.output / 'compilation-result.json').read_bytes())
        self.assertEqual(receipt['executed'], [])
        self.assertEqual(receipt['stage'], 'final')
        self.assertEqual(receipt['artifacts']['network.net.xml']['sha256'], sha256(NETWORK).hexdigest())
        with self.assertRaises(PackageError):
            self.compile()
        self.assertEqual(result.read_bytes(), NETWORK)

    def test_rejects_bad_hash(self):
        self.manifest['artifacts']['network.net.xml']['sha256'] = '0' * 64
        self.assert_rejected('no coincide')

    def test_rejects_incomplete_package(self):
        self.manifest['artifacts'] = {}
        self.assert_rejected('artefacto requerido')

    def test_rejects_unknown_schema(self):
        self.manifest['schemaVersion'] = 2
        self.assert_rejected('Versión de manifiesto')

    def test_rejects_unknown_stage(self):
        self.manifest['stage'] = 'raw-osm'
        self.assert_rejected('Etapa de red')

    def test_rejects_duplicates_and_inconsistent_operations(self):
        for applied, pending in [(['geometry-adjustment'] * 2, []),
                                 (['geometry-adjustment'], ['compound-crossings'])]:
            with self.subTest(applied=applied, pending=pending):
                self.manifest.update(applied=applied, pending=pending)
                self.assert_rejected('duplicadas o inconsistentes')

    def test_rejects_absent_and_external_references(self):
        spec = self.manifest['artifacts']['network.net.xml']
        spec.pop('path')
        self.assert_rejected('Falta la referencia')
        spec['path'] = '../other.xml'
        self.assert_rejected('fuera del paquete')
        spec['path'] = 'missing.xml'
        self.assert_rejected('missing.xml')

    def test_intermediate_runs_only_the_pending_pass(self):
        exe = self.prepare_intermediate()

        def rebuild(output, network, *args):
            self.assertEqual((output / 'network.net.xml').read_bytes(), self.source.read_bytes())
            root = ET.fromstring(NETWORK)
            ET.SubElement(root, 'junction', id=joined_id(CROSSINGS[0]), type='traffic_light')
            final = ET.ElementTree(root)
            final.write(output / 'network.net.xml')
            (output / 'crossing-programs.tll.xml').write_text('<tlLogics/>', encoding='utf-8')
            return final

        with patch('sumo_scenario.network_compiler.sumo_tools', return_value=(None, exe, {})), \
                patch('sumo_scenario.network_compiler.rebuild_crossings', side_effect=rebuild) as call:
            self.compile()
        call.assert_called_once()
        result = json.loads((self.output / 'compilation-result.json').read_bytes())
        self.assertEqual(result['executed'], ['compound-crossings'])

    def prepare_intermediate(self):
        root = ET.fromstring(NETWORK)
        for node in CROSSINGS[0]:
            ET.SubElement(root, 'junction', id=node, type='traffic_light')
        self.source.write_bytes(ET.tostring(root))
        self.manifest['artifacts']['network.net.xml']['sha256'] = sha256(self.source.read_bytes()).hexdigest()
        self.manifest.update(stage='intermediate', applied=['geometry-adjustment'], pending=['compound-crossings'],
                             netconvertSha256=sha256(b'tool').hexdigest())
        exe = self.root / 'netconvert'
        exe.write_bytes(b'tool')
        return exe

    def test_rejects_intermediate_declared_final(self):
        self.prepare_intermediate()
        self.manifest.update(stage='final', applied=['geometry-adjustment', 'compound-crossings'], pending=[])
        self.assert_rejected('La etapa declarada no coincide')

    def test_rejects_pending_operation_without_applicable_crossing(self):
        self.manifest.update(stage='intermediate', applied=['geometry-adjustment'], pending=['compound-crossings'])
        self.assert_rejected('La etapa declarada no coincide')

    def test_failed_or_interrupted_rebuild_never_publishes_receipt(self):
        exe = self.prepare_intermediate()
        for error, expected in [(StudyError('fallo simulado'), PackageError), (KeyboardInterrupt(), KeyboardInterrupt)]:
            with self.subTest(error=type(error).__name__):
                self.output = self.root / type(error).__name__
                with patch('sumo_scenario.network_compiler.sumo_tools', return_value=(None, exe, {})), \
                        patch('sumo_scenario.network_compiler.rebuild_crossings', side_effect=error), \
                        self.assertRaises(expected):
                    self.compile()
                self.assertTrue((self.output / 'network.net.xml').is_file())
                self.assertFalse((self.output / 'compilation-result.json').exists())
