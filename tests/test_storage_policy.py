"""La limpieza automática no sale de results/_tmp ni toca rutas protegidas."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.storage_policy import (
    StorageError, assert_disposable, cleanup_temporary, stage_growth, temporary_directory, write_hash_reference,
)


class StoragePolicyTest(unittest.TestCase):
    def test_growth_reports_added_bytes(self):
        self.assertEqual(stage_growth(10, 15), {"before": 10, "after": 15, "added": 5})

    def test_temporary_directory_stays_under_tmp(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            created = temporary_directory(root, "etapa-prueba")
            self.assertEqual(created.relative_to(root).as_posix(), "results/_tmp/etapa-prueba")
            with self.assertRaises(StorageError):
                temporary_directory(root, "../certificado")

    def test_cleanup_removes_only_the_named_stage(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            kept = temporary_directory(root, "conservar")
            (kept / "nota.txt").write_text("queda", encoding="utf-8")
            disposable = temporary_directory(root, "ensayo")
            (disposable / "copia.xml").write_text("<x/>", encoding="utf-8")
            removed = cleanup_temporary(root, "ensayo")
            self.assertEqual(removed, len("<x/>".encode("utf-8")))
            self.assertFalse(disposable.exists())
            self.assertTrue((kept / "nota.txt").is_file())

    def test_cleanup_refuses_certified_paths(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            certified = root / "results" / "etapa1c5-sector01"
            certified.mkdir(parents=True)
            (certified / "replay.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(StorageError):
                cleanup_temporary(root, "../etapa1c5-sector01")
            self.assertTrue((certified / "replay.json").is_file())

    def test_hash_reference_does_not_copy_the_source(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "red.xml"
            source.write_text("<net/>", encoding="utf-8")
            stage = temporary_directory(root, "etapa-prueba")
            reference = write_hash_reference(stage, source, "red.xml.ref.json")
            self.assertIn(source.name, reference.read_text(encoding="utf-8"))
            self.assertEqual(list(stage.glob("*.xml")), [])

    def test_certified_directory_is_not_disposable(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            certified = root / "results" / "etapa1c5-sector01"
            certified.mkdir(parents=True)
            with self.assertRaises(StorageError):
                assert_disposable(root, certified)
