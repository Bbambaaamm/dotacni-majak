import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]


class CanonicalCodegenTest(unittest.TestCase):
    def generate(self, output: Path) -> None:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate_contracts.py"),
                "--output-root",
                str(output),
            ],
            check=True,
            cwd=ROOT,
        )

    def test_generator_is_deterministic(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = Path(first_tmp)
            second = Path(second_tmp)
            self.generate(first)
            self.generate(second)
            for filename in ("types.ts", "models.py", "manifest.json"):
                self.assertEqual(
                    (first / filename).read_bytes(),
                    (second / filename).read_bytes(),
                    filename,
                )

    def test_manifest_covers_every_canonical_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.generate(output)
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            schema_files = {
                path.name
                for path in (ROOT / "schemas" / "v1").glob("*.schema.json")
            }
            generated_files = {
                item["file"] for item in manifest["schemas"]
            }
            self.assertEqual(generated_files, schema_files)

    def test_generated_typescript_contains_core_interfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.generate(output)
            typescript = (output / "types.ts").read_text(encoding="utf-8")
            self.assertIn("export interface Provider", typescript)
            self.assertIn("export interface GrantCallVersion", typescript)
            self.assertIn("export interface RuleCondition", typescript)
            self.assertIn('"schemaVersion": "1.0.0";', typescript)

    def test_generated_pydantic_models_import_and_reject_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.generate(output)
            module_path = output / "models.py"
            spec = importlib.util.spec_from_file_location(
                "generated_canonical_models",
                module_path,
            )
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)

            provider = module.Provider(
                schemaVersion="1.0.0",
                id="nsa",
                name="Národní sportovní agentura",
                providerType="NATIONAL",
            )
            self.assertEqual(provider.id, "nsa")

            with self.assertRaises(ValidationError):
                module.Provider(
                    schemaVersion="1.0.0",
                    id="nsa",
                    name="NSA",
                    providerType="NATIONAL",
                    inventedField="not allowed",
                )


if __name__ == "__main__":
    unittest.main()
