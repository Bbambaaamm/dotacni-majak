import sqlite3
import unittest
from pathlib import Path


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.paths = sorted((self.root / "migrations").glob("*.sql"))
        self.assertTrue(self.paths, "No migrations found")

    def migrate(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys = ON")
        for path in self.paths:
            connection.executescript(path.read_text(encoding="utf-8"))
        return connection

    def test_all_migrations_apply_in_order(self):
        connection = self.migrate()
        fk = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(fk, 1)

    def test_core_tables_exist(self):
        connection = self.migrate()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        expected = {
            "providers", "programmes", "grant_calls", "grant_call_versions",
            "source_registry", "source_records", "source_documents",
            "document_versions", "document_sections", "field_evidence",
            "grant_deadlines", "funding_scenarios", "grant_requirements",
            "projects", "change_events",
        }
        self.assertTrue(expected.issubset(tables))

    def test_critical_indexes_exist(self):
        connection = self.migrate()
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for name in {
            "idx_grant_calls_status",
            "idx_versions_status_deadline",
            "idx_evidence_entity_field",
            "idx_change_call_created",
        }:
            self.assertIn(name, indexes)

    def test_invalid_support_rate_is_rejected(self):
        connection = self.migrate()
        connection.execute(
            "INSERT INTO providers(id,name,provider_type) VALUES ('p','Provider','NATIONAL')"
        )
        connection.execute(
            "INSERT INTO programmes(id,provider_id,name,funding_origin) VALUES ('pr','p','Program','CZ_NATIONAL')"
        )
        connection.execute(
            "INSERT INTO grant_calls(id,programme_id,canonical_slug,current_status,current_title,first_seen_at,created_at,updated_at) "
            "VALUES ('g','pr','g','OPEN','Grant','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at) "
            "VALUES ('v','g',1,'2026-01-01T00:00:00Z','Grant','OPEN','VERIFIED','2026-01-01T00:00:00Z')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO funding_scenarios(id,grant_call_version_id,name,currency_code,support_rate_max_bps) "
                "VALUES ('f','v','invalid','CZK',10001)"
            )


if __name__ == "__main__":
    unittest.main()
