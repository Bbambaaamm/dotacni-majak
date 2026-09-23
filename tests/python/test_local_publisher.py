import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.local_publish import (
    SearchableGrant,
    render_import_sql,
    sql_text,
)


def grant(content_hash: str, *, title: str = "Sportovní výzva") -> SearchableGrant:
    return SearchableGrant(
        source_id="source:nsa",
        source_code="NSA",
        source_name="Národní sportovní agentura",
        source_base_url="https://nsa.gov.cz/",
        adapter_key="nsa-cz",
        source_external_id="16/2026",
        source_url="https://nsa.gov.cz/dotace/vyzva-16-2026/",
        content_hash=content_hash,
        provider_id="provider:nsa",
        provider_name="Národní sportovní agentura",
        provider_type="NATIONAL",
        programme_id="programme:nsa:investment",
        programme_name="NSA — Investiční výzvy",
        funding_origin="CZ_NATIONAL",
        grant_call_id="grant:nsa:16-2026",
        grant_version_id=f"grant:nsa:16-2026:sha:{content_hash[:24]}",
        canonical_slug="nsa-16-2026",
        title=title,
        summary="Výstavba a technické zhodnocení sportovních zařízení.",
        status="OPEN",
        verification_status="PARTIALLY_VERIFIED",
        captured_at="2026-09-24T00:00:00+00:00",
        submission_close_at="2026-12-31T22:59:59+00:00",
        supported_activities=(
            "Výstavba a technické zhodnocení sportovních zařízení místního významu."
        ),
        keywords="investiční 16/2026",
    )


class LocalPublisherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            self.connection.executescript(path.read_text(encoding="utf-8"))

    def test_sql_text_escapes_apostrophes(self):
        self.assertEqual(sql_text("O'Brien"), "'O''Brien'")

    def test_empty_source_run_is_rejected(self):
        with self.assertRaises(ValueError):
            render_import_sql(
                [],
                source_id="source:nsa",
                source_code="NSA",
                source_name="NSA",
                adapter_version="1",
            )

    def test_same_import_is_idempotent(self):
        item = grant("a" * 64)
        sql = render_import_sql(
            [item],
            source_id="source:nsa",
            source_code="NSA",
            source_name="NSA",
            adapter_version="0.1.0",
            captured_at="2026-09-24T00:00:00+00:00",
        )
        self.connection.executescript(sql)
        self.connection.executescript(sql)

        versions = self.connection.execute(
            "SELECT COUNT(*) FROM grant_call_versions WHERE grant_call_id=?",
            (item.grant_call_id,),
        ).fetchone()[0]
        search_docs = self.connection.execute(
            "SELECT COUNT(*) FROM grant_search_documents",
        ).fetchone()[0]
        source_records = self.connection.execute(
            "SELECT COUNT(*) FROM source_records",
        ).fetchone()[0]

        self.assertEqual(versions, 1)
        self.assertEqual(search_docs, 1)
        self.assertEqual(source_records, 1)

    def test_changed_content_creates_new_version_and_replaces_search_document(self):
        first = grant("a" * 64, title="Sportovní výzva v1")
        second = grant("b" * 64, title="Sportovní výzva v2")

        self.connection.executescript(
            render_import_sql(
                [first],
                source_id="source:nsa",
                source_code="NSA",
                source_name="NSA",
                adapter_version="0.1.0",
                captured_at="2026-09-24T00:00:00+00:00",
            )
        )
        self.connection.executescript(
            render_import_sql(
                [second],
                source_id="source:nsa",
                source_code="NSA",
                source_name="NSA",
                adapter_version="0.1.0",
                captured_at="2026-09-24T01:00:00+00:00",
            )
        )

        versions = self.connection.execute(
            "SELECT COUNT(*) FROM grant_call_versions WHERE grant_call_id=?",
            (first.grant_call_id,),
        ).fetchone()[0]
        search_rows = self.connection.execute(
            "SELECT grant_call_version_id,title FROM grant_search_documents",
        ).fetchall()
        current = self.connection.execute(
            "SELECT current_version_id,current_title FROM grant_calls WHERE id=?",
            (first.grant_call_id,),
        ).fetchone()

        self.assertEqual(versions, 2)
        self.assertEqual(search_rows, [(second.grant_version_id, second.title)])
        self.assertEqual(current, (second.grant_version_id, second.title))

    def test_search_index_contains_supported_activity_text(self):
        item = grant("c" * 64)
        self.connection.executescript(
            render_import_sql(
                [item],
                source_id="source:nsa",
                source_code="NSA",
                source_name="NSA",
                adapter_version="0.1.0",
                captured_at="2026-09-24T00:00:00+00:00",
            )
        )
        count = self.connection.execute(
            "SELECT COUNT(*) FROM grant_search_fts "
            "WHERE grant_search_fts MATCH 'sportovnich zarizeni'"
        ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
