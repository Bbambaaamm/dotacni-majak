import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.state import IngestionState, PresenceState


class IngestionStateTest(unittest.TestCase):
    def test_terminal_and_safety_states_exist(self):
        self.assertEqual(IngestionState.COMPLETED.value, "COMPLETED")
        self.assertEqual(IngestionState.QUARANTINED.value, "QUARANTINED")
        self.assertEqual(PresenceState.CONFIRMED_MISSING.value, "CONFIRMED_MISSING")


if __name__ == "__main__":
    unittest.main()
