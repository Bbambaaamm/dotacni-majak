from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

class RepositoryError(RuntimeError):
    """Repository-level failure (constraint violation, missing row, etc.)."""


class NotFoundError(RepositoryError):
    """Requested row did not exist."""


class SqliteRepository:
    """Generic D1-compatible SQLite repository base.

    The runtime owns the sqlite3.Connection (D1 in production, :memory: in tests).
    Concrete repositories subclass this and declare their own queries.  The module
    intentionally stays in the D1-compatible SQL subset so a remote D1 transport can
    implement the same contract without changing callers.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        table_name: str,
        row_factory: bool = True,
    ) -> None:
        self.connection = connection
        self.table_name = table_name
        if row_factory:
            self.connection.row_factory = sqlite3.Row
        # Use autocommit so we can control BEGIN IMMEDIATE explicitly.
        self.connection.isolation_level = None
        self.connection.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    @contextmanager
    def transaction(self):
        """Begin an IMMEDIATE transaction; commit on success, rollback on exception."""
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    id: str
    name: str
    short_name: str | None
    provider_type: str
    ico: str | None
    country_code: str | None
    official_url: str | None


@dataclass(frozen=True, slots=True)
class ProgrammeRecord:
    id: str
    provider_id: str
    code: str | None
    name: str
    funding_origin: str
    currency_default: str | None
    valid_from: str | None
    valid_to: str | None
    official_url: str | None


@dataclass(frozen=True, slots=True)
class GrantCallRecord:
    id: str
    programme_id: str
    canonical_code: str | None
    canonical_slug: str
    current_version_id: str | None
    current_status: str
    current_title: str
    first_seen_at: str
    first_published_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class GrantCallVersionRecord:
    id: str
    grant_call_id: str
    version_number: int
    captured_at: str
    title: str
    summary: str | None
    status: str
    published_at: str | None
    submission_open_at: str | None
    submission_close_at: str | None
    official_detail_url: str | None
    currency_code: str | None
    normalization_version: str | None
    content_hash: str
    verification_status: str
    created_at: str


class SqliteProviderRepository(SqliteRepository):
    """D1-compatible repository for the canonical ``providers`` table.

    Proof of concept for the #226 repository pattern: one concrete repo per
    canonical entity (providers, programmes, grant_calls, versions, documents,
    evidence), all sharing the generic ``SqliteRepository`` base.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, table_name="providers")

    def get_by_id(self, id: str) -> ProviderRecord | None:
        row = self.execute(
            "SELECT id, name, short_name, provider_type, ico, country_code, official_url "
            "FROM providers WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            return None
        return self._provider_from_row(row)

    def list_by_type(self, provider_type: str) -> list[ProviderRecord]:
        rows = self.execute(
            "SELECT id, name, short_name, provider_type, ico, country_code, official_url "
            "FROM providers WHERE provider_type = ? ORDER BY name",
            (provider_type,),
        ).fetchall()
        return [self._provider_from_row(row) for row in rows]

    def create(self, record: ProviderRecord) -> ProviderRecord:
        with self.transaction():
            self.execute(
                """INSERT OR IGNORE INTO providers(
                     id, name, short_name, provider_type, ico, country_code, official_url
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.name,
                    record.short_name,
                    record.provider_type,
                    record.ico,
                    record.country_code,
                    record.official_url,
                ),
            )
            row = self.execute(
                "SELECT id, name, short_name, provider_type, ico, country_code, official_url "
                "FROM providers WHERE id = ?",
                (record.id,),
            ).fetchone()
            if row is None:
                raise RepositoryError(f"failed to persist provider {record.id!r}")
            return self._provider_from_row(row)

    def list_all(self) -> list[ProviderRecord]:
        rows = self.execute(
            "SELECT id, name, short_name, provider_type, ico, country_code, official_url "
            "FROM providers ORDER BY name",
        ).fetchall()
        return [self._provider_from_row(row) for row in rows]

    def _provider_from_row(self, row: sqlite3.Row) -> ProviderRecord:
        return ProviderRecord(
            id=row["id"],
            name=row["name"],
            short_name=row["short_name"],
            provider_type=row["provider_type"],
            ico=row["ico"],
            country_code=row["country_code"],
            official_url=row["official_url"],
        )


class SqliteProgrammeRepository(SqliteRepository):
    """D1-compatible repository for the canonical ``programmes`` table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, table_name="programmes")

    def get_by_id(self, id: str) -> ProgrammeRecord | None:
        row = self.execute(
            "SELECT id, provider_id, code, name, funding_origin, "
            "currency_default, valid_from, valid_to, official_url "
            "FROM programmes WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            return None
        return self._programme_from_row(row)

    def list_by_provider(self, provider_id: str) -> list[ProgrammeRecord]:
        rows = self.execute(
            "SELECT id, provider_id, code, name, funding_origin, "
            "currency_default, valid_from, valid_to, official_url "
            "FROM programmes WHERE provider_id = ? ORDER BY name",
            (provider_id,),
        ).fetchall()
        return [self._programme_from_row(row) for row in rows]

    def upsert(self, record: ProgrammeRecord) -> ProgrammeRecord:
        with self.transaction():
            self.execute(
                """INSERT INTO programmes(
                       id, provider_id, code, name, funding_origin,
                       currency_default, valid_from, valid_to, official_url
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       provider_id = excluded.provider_id,
                       code = excluded.code,
                       name = excluded.name,
                       funding_origin = excluded.funding_origin,
                       currency_default = excluded.currency_default,
                       valid_from = excluded.valid_from,
                       valid_to = excluded.valid_to,
                       official_url = excluded.official_url""",
                (
                    record.id, record.provider_id, record.code,
                    record.name, record.funding_origin,
                    record.currency_default, record.valid_from,
                    record.valid_to, record.official_url,
                ),
            )
            row = self.execute(
                "SELECT id, provider_id, code, name, funding_origin, "
                "currency_default, valid_from, valid_to, official_url "
                "FROM programmes WHERE id = ?",
                (record.id,),
            ).fetchone()
            if row is None:
                raise RepositoryError(
                    f"failed to persist programme {record.id!r}"
                )
            return self._programme_from_row(row)

    def _programme_from_row(self, row: sqlite3.Row) -> ProgrammeRecord:
        return ProgrammeRecord(
            id=row["id"],
            provider_id=row["provider_id"],
            code=row["code"],
            name=row["name"],
            funding_origin=row["funding_origin"],
            currency_default=row["currency_default"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            official_url=row["official_url"],
        )


class SqliteGrantCallRepository(SqliteRepository):
    """D1-compatible repository for the canonical ``grant_calls`` table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, table_name="grant_calls")

    def get_by_id(self, id: str) -> GrantCallRecord | None:
        row = self.execute(
            "SELECT id, programme_id, canonical_code, canonical_slug, "
            "current_version_id, current_status, current_title, "
            "first_seen_at, first_published_at, created_at, updated_at "
            "FROM grant_calls WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            return None
        return self._grant_call_from_row(row)

    def get_by_slug(self, canonical_slug: str) -> GrantCallRecord | None:
        row = self.execute(
            "SELECT id, programme_id, canonical_code, canonical_slug, "
            "current_version_id, current_status, current_title, "
            "first_seen_at, first_published_at, created_at, updated_at "
            "FROM grant_calls WHERE canonical_slug = ?",
            (canonical_slug,),
        ).fetchone()
        if row is None:
            return None
        return self._grant_call_from_row(row)

    def create_or_update(self, record: GrantCallRecord) -> GrantCallRecord:
        with self.transaction():
            existing = self.execute(
                "SELECT programme_id, canonical_slug FROM grant_calls WHERE id = ?",
                (record.id,),
            ).fetchone()
            slug_owner = self.execute(
                "SELECT id FROM grant_calls WHERE canonical_slug = ?",
                (record.canonical_slug,),
            ).fetchone()
            if slug_owner is not None and str(slug_owner["id"]) != record.id:
                raise RepositoryError(
                    f"canonical_slug {record.canonical_slug!r} "
                    "belongs to another GrantCall"
                )
            if existing is None:
                self.execute(
                    """INSERT INTO grant_calls(
                           id, programme_id, canonical_code, canonical_slug,
                           current_version_id, current_status, current_title,
                           first_seen_at, first_published_at, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.id, record.programme_id, record.canonical_code,
                        record.canonical_slug, record.current_version_id,
                        record.current_status, record.current_title,
                        record.first_seen_at, record.first_published_at,
                        record.created_at, record.updated_at,
                    ),
                )
            elif (
                str(existing["programme_id"]) != record.programme_id
                or str(existing["canonical_slug"]) != record.canonical_slug
            ):
                raise RepositoryError(
                    "stable GrantCall identity conflicts with existing "
                    "programme/slug"
                )
            else:
                self.execute(
                    """UPDATE grant_calls
                       SET current_version_id = ?,
                           current_status = ?,
                           current_title = ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (
                        record.current_version_id,
                        record.current_status,
                        record.current_title,
                        record.updated_at,
                        record.id,
                    ),
                )
            return self._fetch_one(record.id)

    def update_current_version(
        self,
        *,
        id: str,
        version_id: str,
        current_status: str,
        current_title: str,
        updated_at: str,
    ) -> GrantCallRecord:
        result = self.execute(
            """UPDATE grant_calls
               SET current_version_id = ?,
                   current_status = ?,
                   current_title = ?,
                   updated_at = ?
               WHERE id = ?""",
            (version_id, current_status, current_title, updated_at, id),
        )
        if result.rowcount != 1:
            raise NotFoundError(id)
        self.connection.commit()
        return self._fetch_one(id)

    def _fetch_one(self, id: str) -> GrantCallRecord:
        row = self.execute(
            "SELECT id, programme_id, canonical_code, canonical_slug, "
            "current_version_id, current_status, current_title, "
            "first_seen_at, first_published_at, created_at, updated_at "
            "FROM grant_calls WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"grant_call {id!r} was not persisted")
        return self._grant_call_from_row(row)

    def _grant_call_from_row(self, row: sqlite3.Row) -> GrantCallRecord:
        return GrantCallRecord(
            id=row["id"],
            programme_id=row["programme_id"],
            canonical_code=row["canonical_code"],
            canonical_slug=row["canonical_slug"],
            current_version_id=row["current_version_id"],
            current_status=row["current_status"],
            current_title=row["current_title"],
            first_seen_at=row["first_seen_at"],
            first_published_at=row["first_published_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SqliteGrantCallVersionRepository(SqliteRepository):
    """D1-compatible repository for the immutable ``grant_call_versions`` table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, table_name="grant_call_versions")

    def get_by_id(self, id: str) -> GrantCallVersionRecord | None:
        row = self.execute(
            "SELECT id, grant_call_id, version_number, captured_at, "
            "title, summary, status, published_at, submission_open_at, "
            "submission_close_at, official_detail_url, currency_code, "
            "normalization_version, content_hash, verification_status, "
            "created_at FROM grant_call_versions WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            return None
        return self._version_from_row(row)

    def get_by_content_hash(
        self,
        grant_call_id: str,
        content_hash: str,
    ) -> GrantCallVersionRecord | None:
        row = self.execute(
            "SELECT id, grant_call_id, version_number, captured_at, "
            "title, summary, status, published_at, submission_open_at, "
            "submission_close_at, official_detail_url, currency_code, "
            "normalization_version, content_hash, verification_status, "
            "created_at FROM grant_call_versions "
            "WHERE grant_call_id = ? AND content_hash = ?",
            (grant_call_id, content_hash),
        ).fetchone()
        if row is None:
            return None
        return self._version_from_row(row)

    def next_version_number(self, grant_call_id: str) -> int:
        row = self.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 "
            "FROM grant_call_versions WHERE grant_call_id = ?",
            (grant_call_id,),
        ).fetchone()
        return int(row[0])

    def list_by_call(self, grant_call_id: str) -> list[GrantCallVersionRecord]:
        rows = self.execute(
            "SELECT id, grant_call_id, version_number, captured_at, "
            "title, summary, status, published_at, submission_open_at, "
            "submission_close_at, official_detail_url, currency_code, "
            "normalization_version, content_hash, verification_status, "
            "created_at FROM grant_call_versions "
            "WHERE grant_call_id = ? ORDER BY version_number DESC",
            (grant_call_id,),
        ).fetchall()
        return [self._version_from_row(row) for row in rows]

    def create(self, record: GrantCallVersionRecord) -> GrantCallVersionRecord:
        with self.transaction():
            self.execute(
                """INSERT INTO grant_call_versions(
                       id, grant_call_id, version_number, captured_at,
                       effective_from, effective_to, title, summary, status,
                       published_at, submission_open_at, submission_close_at,
                       application_url, official_detail_url, currency_code,
                       normalization_version, content_hash, verification_status,
                       created_at
                   ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id, record.grant_call_id, record.version_number,
                    record.captured_at, record.title, record.summary,
                    record.status, record.published_at,
                    record.submission_open_at, record.submission_close_at,
                    None, record.official_detail_url, record.currency_code,
                    record.normalization_version, record.content_hash,
                    record.verification_status, record.created_at,
                ),
            )
        return self.get_by_id(record.id)  # type: ignore[return-value]

    def _version_from_row(self, row: sqlite3.Row) -> GrantCallVersionRecord:
        return GrantCallVersionRecord(
            id=row["id"],
            grant_call_id=row["grant_call_id"],
            version_number=int(row["version_number"]),
            captured_at=row["captured_at"],
            title=row["title"],
            summary=row["summary"],
            status=row["status"],
            published_at=row["published_at"],
            submission_open_at=row["submission_open_at"],
            submission_close_at=row["submission_close_at"],
            official_detail_url=row["official_detail_url"],
            currency_code=row["currency_code"],
            normalization_version=row["normalization_version"],
            content_hash=row["content_hash"],
            verification_status=row["verification_status"],
            created_at=row["created_at"],
        )
