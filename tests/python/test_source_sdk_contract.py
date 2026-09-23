import importlib.util
import unittest
from pathlib import Path


class SourceSdkContractTest(unittest.TestCase):
    def test_models_module_exists(self):
        root = Path(__file__).resolve().parents[2]
        path = root / "packages" / "source-sdk" / "src" / "dotacni_majak_source_sdk" / "models.py"
        self.assertTrue(path.exists())
        spec = importlib.util.spec_from_file_location("source_sdk_models", path)
        self.assertIsNotNone(spec)


if __name__ == "__main__":
    unittest.main()
