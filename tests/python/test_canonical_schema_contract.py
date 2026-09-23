import json
import unittest
from pathlib import Path


class CanonicalSchemaContractTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.schemas = sorted((self.root / "schemas" / "v1").glob("*.schema.json"))

    def test_core_domains_are_present(self):
        names = {p.name for p in self.schemas}
        expected = {
            "provider.schema.json",
            "programme.schema.json",
            "grant-call.schema.json",
            "grant-call-version.schema.json",
            "source-document.schema.json",
            "document-version.schema.json",
            "field-evidence.schema.json",
            "grant-deadline.schema.json",
            "funding-scenario.schema.json",
            "grant-requirement.schema.json",
            "project.schema.json",
            "change-event.schema.json",
        }
        self.assertTrue(expected.issubset(names))

    def test_all_v1_schemas_are_closed_and_versioned(self):
        for path in self.schemas:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(payload["additionalProperties"], path.name)
            self.assertEqual(payload["properties"]["schemaVersion"]["const"], "1.0.0", path.name)
            self.assertIn("schemaVersion", payload["required"], path.name)


if __name__ == "__main__":
    unittest.main()
