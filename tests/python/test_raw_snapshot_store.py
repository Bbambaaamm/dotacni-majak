import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore


class LocalRawSnapshotStoreTest(unittest.TestCase):
    def test_same_content_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawSnapshotStore(tmp)
            when = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)

            first = store.put(
                source_code="NSA",
                source_url="https://example.com/a.pdf",
                content=b"same content",
                mime_type="application/pdf",
                retrieved_at=when,
            )
            second = store.put(
                source_code="NSA",
                source_url="https://example.com/b.pdf",
                content=b"same content",
                mime_type="application/pdf",
                retrieved_at=when,
            )

            self.assertEqual(first.sha256, second.sha256)
            self.assertEqual(first.object_key, second.object_key)
            objects = list(Path(tmp).rglob("*.bin"))
            self.assertEqual(len(objects), 1)
            self.assertEqual(store.get_bytes(first), b"same content")

    def test_different_content_gets_different_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawSnapshotStore(tmp)
            a = store.put(
                source_code="JDP",
                source_url="https://example.com/a",
                content=b"a",
                mime_type="text/html",
            )
            b = store.put(
                source_code="JDP",
                source_url="https://example.com/b",
                content=b"b",
                mime_type="text/html",
            )
            self.assertNotEqual(a.object_key, b.object_key)

    def test_rejects_unsafe_source_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawSnapshotStore(tmp)
            with self.assertRaises(ValueError):
                store.put(
                    source_code="../escape",
                    source_url="https://example.com",
                    content=b"x",
                    mime_type="text/plain",
                )

    def test_detects_content_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawSnapshotStore(tmp)
            snapshot = store.put(
                source_code="EU",
                source_url="https://example.com/data",
                content=b"original",
                mime_type="application/json",
            )
            path = Path(tmp) / snapshot.object_key
            path.write_bytes(b"tampered")
            with self.assertRaises(RuntimeError):
                store.get_bytes(snapshot)


if __name__ == "__main__":
    unittest.main()
