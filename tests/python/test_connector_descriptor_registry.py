import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))

from dotacni_majak_source_sdk import (
    AdapterContext,
    ArtifactFetchResult,
    ConnectorDescriptorError,
    ConnectorRegistry,
    DiscoveryPage,
    HealthReport,
    RecordFetchResult,
    SourceAdapter,
    SourceDescriptor,
    load_connector_descriptor,
)


def descriptor_yaml(*, key="demo", code="DEMO", import_path=None):
    import_path = import_path or f"dotacni_majak_{key.replace('-', '_')}.adapter:DemoAdapter"
    return f"""schemaVersion: 1
adapter_key: {key}
import_path: {import_path}
source:
  code: {code}
  name: Demo
  authority: OFFICIAL
  country_code: CZ
  base_url: https://example.com/
  retrieval_modes: [HTML]
  allowed_hosts: [example.com]
  allowed_post_paths: []
  normal_refresh_minutes: 60
  max_concurrency: 1
  requests_per_second: 1.0
  disappearance_confirmation_runs: 3
  adapter_version: 1.0.0
"""


class ConnectorDescriptorTest(unittest.TestCase):
    def test_loads_valid_descriptor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "descriptor.yaml"
            path.write_text(descriptor_yaml(), encoding="utf-8")
            descriptor = load_connector_descriptor(path)
            self.assertEqual(descriptor.adapter_key, "demo")
            self.assertEqual(descriptor.source.code, "DEMO")

    def test_duplicate_yaml_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "descriptor.yaml"
            path.write_text(
                descriptor_yaml() + "\nadapter_key: duplicate\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConnectorDescriptorError):
                load_connector_descriptor(path)

    def test_wildcard_host_and_unsafe_post_path_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "descriptor.yaml"
            value = descriptor_yaml().replace(
                "allowed_hosts: [example.com]",
                "allowed_hosts: ['*.example.com']",
            )
            path.write_text(value, encoding="utf-8")
            with self.assertRaises(ConnectorDescriptorError):
                load_connector_descriptor(path)

            path.write_text(
                descriptor_yaml().replace(
                    "allowed_post_paths: []",
                    "allowed_post_paths: ['/../admin']",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConnectorDescriptorError):
                load_connector_descriptor(path)

    def test_registry_rejects_duplicate_source_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for key in ("one", "two"):
                directory = root / key
                directory.mkdir()
                (directory / "descriptor.yaml").write_text(
                    descriptor_yaml(key=key, code="SAME"),
                    encoding="utf-8",
                )
            with self.assertRaises(ConnectorDescriptorError):
                ConnectorRegistry.from_connectors_root(root)

    def test_runtime_descriptor_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "demo"
            directory.mkdir()
            (directory / "descriptor.yaml").write_text(
                descriptor_yaml(),
                encoding="utf-8",
            )
            registry = ConnectorRegistry.from_connectors_root(root)

            package = types.ModuleType("dotacni_majak_demo")
            package.__path__ = []
            module = types.ModuleType("dotacni_majak_demo.adapter")

            class DemoAdapter(SourceAdapter):
                descriptor = SourceDescriptor(
                    code="DIFFERENT",
                    name="Demo",
                    authority="OFFICIAL",
                    country_code="CZ",
                    base_url="https://example.com/",
                    retrieval_modes=["HTML"],
                    allowed_hosts=["example.com"],
                    adapter_version="1.0.0",
                    normal_refresh_minutes=60,
                    max_concurrency=1,
                    requests_per_second=1.0,
                    disappearance_confirmation_runs=3,
                )

                async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
                    raise NotImplementedError

                async def discover(self, ctx, checkpoint) -> DiscoveryPage:
                    raise NotImplementedError

                async def fetch_record(self, ctx, item, validators=None) -> RecordFetchResult:
                    raise NotImplementedError

                async def fetch_artifact(self, ctx, artifact, validators=None) -> ArtifactFetchResult:
                    raise NotImplementedError

            module.DemoAdapter = DemoAdapter
            old_package = sys.modules.get("dotacni_majak_demo")
            old_module = sys.modules.get("dotacni_majak_demo.adapter")
            sys.modules["dotacni_majak_demo"] = package
            sys.modules["dotacni_majak_demo.adapter"] = module
            try:
                with self.assertRaises(ConnectorDescriptorError):
                    registry.load_adapter_class("demo")
            finally:
                if old_package is None:
                    sys.modules.pop("dotacni_majak_demo", None)
                else:
                    sys.modules["dotacni_majak_demo"] = old_package
                if old_module is None:
                    sys.modules.pop("dotacni_majak_demo.adapter", None)
                else:
                    sys.modules["dotacni_majak_demo.adapter"] = old_module


if __name__ == "__main__":
    unittest.main()
