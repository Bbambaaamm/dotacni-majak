import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))

from dotacni_majak_source_sdk import ConnectorRegistry


class RepositoryConnectorDescriptorTest(unittest.TestCase):
    def test_reference_connector_descriptors_are_valid_and_unique(self):
        registry = ConnectorRegistry.from_connectors_root(ROOT / "connectors")
        keys = {registration.descriptor.adapter_key for registration in registry.registrations()}
        self.assertTrue(
            {"eu-funding", "nsa", "dotaceeu", "plzensky"}.issubset(keys)
        )

    def test_installed_reference_connectors_do_not_drift(self):
        registry = ConnectorRegistry.from_connectors_root(ROOT / "connectors")
        # These connector packages are installed by the main CI workflow.
        for key in ("nsa", "dotaceeu", "plzensky"):
            adapter_class = registry.load_adapter_class(key)
            self.assertEqual(
                adapter_class.descriptor.code,
                registry.by_adapter_key(key).descriptor.source.code,
            )


if __name__ == "__main__":
    unittest.main()
