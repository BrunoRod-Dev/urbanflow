"""La pantalla de Maldonado puede abrir la corrida certificada sin copiarla."""

from hashlib import sha256
from pathlib import Path
import unittest

from src.study_server import published_run


ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "results/etapa1c5-sector01/candidata/01c5b202611140000000000000000001/replay.json"
REPLAY_SHA256 = "03b534e910cd373360eb595fa463dff5e7ee9f743368b67378c7e6aca141080b"


def digest(path):
    hashed = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


class PublishedRunTest(unittest.TestCase):
    def test_sector_manifest_points_at_the_certified_replay(self):
        directory = published_run("01c5b202611140000000000000000001")
        self.assertEqual(directory, REPLAY.parent)
        self.assertEqual(digest(REPLAY), REPLAY_SHA256)
        self.assertEqual(REPLAY.stat().st_size, 1084990)
        self.assertIsNone(published_run("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
        self.assertIsNone(published_run("../replay"))
