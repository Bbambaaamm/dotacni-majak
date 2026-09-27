import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.canonical_repository import (
    GrantCallRecord,
    GrantCallVersionRecord,
    NotFoundError,
    ProgrammeRecord,
    ProviderRecord,
    RepositoryError,
    SqliteGrantCallRepository,
    SqliteGrantCallVersionRepository,
    SqliteProgrammeRepository,
    SqliteProviderRepository,
)

T0 = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


def _seed_provider(conn: sqlite3.Connection, provider_id: str = "p1") -> None:
    conn.execute(
        "INSERT INTO providers(id,name,provider_type) VALUES (?, ?, 'NATIONAL')",
        (provider_id, "Test Provider"),
    )


def _seed_programme(
    conn: sqlite3.Connection,
    programme_id: str = "pr1",
    provider_id: str = "p1",
) -> None:
    conn.execute(
        "INSERT INTO programmes(id,provider_id,name,funding_origin) "
        "VALUES (?, ?, ?, 'CZ_NATIONAL')",
        (programme_id, provider_id, "Test Programme"),
    )


def _seed_grant_call(
    conn: sqlite3.Connection,
    call_id: str = "gc1",
    programme_id: str = "pr1",
) -> None:
    conn.execute(
        "INSERT INTO grant_calls(id,programme_id,canonical_slug,"
        "current_status,current_title,first_seen_at,created_at,updated_at) "
        "VALUES (?, ?, ?, 'OPEN', 'Test Call', ?, ?, ?)",
        (
            call_id, programme_id, "test-call",
            T0.isoformat(), T0.isoformat(), T0.isoformat(),
        ),
    )


class SqliteProviderRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = migrated_connection()
        self.repo = SqliteProviderRepository(self.conn)

    def test_create_and_get_by_id(self) -> None:
        record = ProviderRecord(
            id="p1", name="Ministry of Education", short_name=None,
            provider_type="NATIONAL", ico=None, country_code="CZ",
            official_url="https://mŠMT.cz",
        )
        result = self.repo.create(record)
        self.assertEqual(result.id, "p1")
        self.assertEqual(result.name, "Ministry of Education")
        self.assertEqual(result.provider_type, "NATIONAL")
        got = self.repo.get_by_id("p1")
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.official_url, "https://mŠMT.cz")

    def test_get_unknown_returns_none(self) -> None:
        self.assertIsNone(self.repo.get_by_id("nonexistent"))

    def test_create_idempotent(self) -> None:
        record = ProviderRecord(
            id="p1", name="Provider", short_name=None,
            provider_type="EU", ico=None, country_code=None,
            official_url=None,
        )
        first = self.repo.create(record)
        second = self.repo.create(record)
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.repo.list_all(), [first])


class SqliteProgrammeRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = migrated_connection()
        _seed_provider(self.conn, "p1")
        self.repo = SqliteProgrammeRepository(self.conn)

    def test_get_by_id_after_upsert(self) -> None:
        record = ProgrammeRecord(
            id="pr1", provider_id="p1", code="PROG1",
            name="Test Programme", funding_origin="CZ_NATIONAL",
            currency_default="CZK", valid_from="2026-01-01",
            valid_to=None, official_url="https://example.com",
        )
        self.repo.upsert(record)
        got = self.repo.get_by_id("pr1")
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.funding_origin, "CZ_NATIONAL")
        self.assertEqual(got.currency_default, "CZK")

    def test_list_by_provider(self) -> None:
        self.conn.execute(
            "INSERT INTO programmes(id,provider_id,name,funding_origin) "
            "VALUES ('pr1','p1','First','CZ_NATIONAL')"
        )
        self.conn.execute(
            "INSERT INTO programmes(id,provider_id,name,funding_origin) "
            "VALUES ('pr2','p1','Second','CZ_NATIONAL')"
        )
        result = self.repo.list_by_provider("p1")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "First")

    def test_upsert_updates_existing(self) -> None:
        original = ProgrammeRecord(
            id="pr1", provider_id="p1", code=None,
            name="Original", funding_origin="CZ_NATIONAL",
            currency_default=None, valid_from=None, valid_to=None,
            official_url=None,
        )
        self.repo.upsert(original)
        updated = ProgrammeRecord(
            id="pr1", provider_id="p1", code="NEW",
            name="Updated Name", funding_origin="CZ_REGION",
            currency_default="EUR", valid_from=None, valid_to=None,
            official_url="https://updated.example.com",
        )
        self.repo.upsert(updated)
        got = self.repo.get_by_id("pr1")
        assert got is not None
        self.assertEqual(got.name, "Updated Name")
        self.assertEqual(got.code, "NEW")
        self.assertEqual(got.funding_origin, "CZ_REGION")


class SqliteGrantCallRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = migrated_connection()
        _seed_provider(self.conn, "p1")
        _seed_programme(self.conn, "pr1", "p1")
        self.repo = SqliteGrantCallRepository(self.conn)

    def _make_record(
        self,
        id: str = "gc1",
        programme_id: str = "pr1",
        **kwargs: object,
    ) -> GrantCallRecord:
        defaults: dict[str, object] = dict(
            id=id, programme_id=programme_id,
            canonical_code="EXT-1", canonical_slug="test-call",
            current_version_id=None, current_status="OPEN",
            current_title="Test Call",
            first_seen_at=T0.isoformat(),
            first_published_at=None,
            created_at=T0.isoformat(),
            updated_at=T0.isoformat(),
        )
        defaults.update(kwargs)
        return GrantCallRecord(**defaults)

    def test_create_and_get_by_id(self) -> None:
        record = self._make_record()
        self.repo.create_or_update(record)
        got = self.repo.get_by_id("gc1")
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.canonical_slug, "test-call")
        self.assertEqual(got.current_status, "OPEN")
        self.assertIsNone(got.current_version_id)

    def test_get_by_slug(self) -> None:
        self.repo.create_or_update(self._make_record())
        got = self.repo.get_by_slug("test-call")
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.id, "gc1")

    def test_update_existing(self) -> None:
        record = self._make_record()
        self.repo.create_or_update(record)
        updated = self._make_record(
            current_version_id="gcv1",
            current_status="CLOSED",
            current_title="Updated Title",
        )
        result = self.repo.create_or_update(updated)
        self.assertEqual(result.current_version_id, "gcv1")
        self.assertEqual(result.current_status, "CLOSED")
        self.assertEqual(result.current_title, "Updated Title")

    def test_slug_conflict_raises(self) -> None:
        self.repo.create_or_update(self._make_record(id="gc1", canonical_slug="shared"))
        other = self._make_record(id="gc2", canonical_slug="shared")
        with self.assertRaises(RepositoryError):
            self.repo.create_or_update(other)

    def test_programme_conflict_raises(self) -> None:
        _seed_programme(self.conn, "pr2", "p1")
        self.repo.create_or_update(self._make_record(id="gc1", programme_id="pr1"))
        conflict = self._make_record(id="gc1", programme_id="pr2")
        with self.assertRaises(RepositoryError):
            self.repo.create_or_update(conflict)

    def test_update_current_version(self) -> None:
        self.repo.create_or_update(self._make_record())
        result = self.repo.update_current_version(
            id="gc1", version_id="gcv-new",
            current_status="CLOSED", current_title="Closed Title",
            updated_at="2026-09-25T00:00:00+00:00",
        )
        self.assertEqual(result.current_version_id, "gcv-new")
        self.assertEqual(result.current_status, "CLOSED")

    def test_update_current_version_unknown_raises(self) -> None:
        with self.assertRaises(NotFoundError):
            self.repo.update_current_version(
                id="nonexistent", version_id="gcv1",
                current_status="OPEN", current_title="T",
                updated_at="2026-09-25T00:00:00+00:00",
            )


class SqliteGrantCallVersionRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = migrated_connection()
        _seed_provider(self.conn, "p1")
        _seed_programme(self.conn, "pr1", "p1")
        _seed_grant_call(self.conn, "gc1", "pr1")
        self.repo = SqliteGrantCallVersionRepository(self.conn)

    def _make_record(
        self,
        id: str = "gcv1",
        grant_call_id: str = "gc1",
        version_number: int = 1,
        **kwargs: object,
    ) -> GrantCallVersionRecord:
        defaults: dict[str, object] = dict(
            id=id, grant_call_id=grant_call_id, version_number=version_number,
            captured_at=T0.isoformat(), title="Version 1",
            summary=None, status="OPEN", published_at=None,
            submission_open_at=None, submission_close_at=None,
            official_detail_url=None, currency_code="CZK",
            normalization_version="v0.1",
            content_hash="a" * 64,
            verification_status="VERIFIED",
            created_at=T0.isoformat(),
        )
        defaults.update(kwargs)
        return GrantCallVersionRecord(**defaults)

    def test_next_version_number_first(self) -> None:
        self.assertEqual(self.repo.next_version_number("gc1"), 1)

    def test_next_version_number_after_create(self) -> None:
        self.repo.create(self._make_record())
        self.assertEqual(self.repo.next_version_number("gc1"), 2)

    def test_create_and_get_by_id(self) -> None:
        record = self._make_record()
        result = self.repo.create(record)
        self.assertEqual(result.id, "gcv1")
        self.assertEqual(result.title, "Version 1")
        got = self.repo.get_by_id("gcv1")
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.content_hash, "a" * 64)

    def test_get_by_content_hash(self) -> None:
        self.repo.create(self._make_record(content_hash="b" * 64))
        got = self.repo.get_by_content_hash("gc1", "b" * 64)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.title, "Version 1")

    def test_get_by_content_hash_unknown_returns_none(self) -> None:
        self.assertIsNone(
            self.repo.get_by_content_hash("gc1", "c" * 64)
        )

    def test_list_by_call_order(self) -> None:
        self.repo.create(self._make_record(id="gcv1", version_number=1, content_hash="a" * 64))
        self.repo.create(self._make_record(id="gcv2", version_number=2, content_hash="b" * 64))
        result = self.repo.list_by_call("gc1")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].version_number, 2)
        self.assertEqual(result[1].version_number, 1)


if __name__ == "__main__":
    unittest.main()
