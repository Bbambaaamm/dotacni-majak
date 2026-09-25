import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_source_fixtures import validate_repository_source_fixtures


class SourceFixtureManifestTest(unittest.TestCase):
    def test_managed_source_fixtures_are_locked_and_reviewed(self):
        result = validate_repository_source_fixtures(ROOT)
        self.assertGreaterEqual(result.manifests, 4)
        self.assertGreaterEqual(result.fixtures, 9)


if __name__ == "__main__":
    unittest.main()
