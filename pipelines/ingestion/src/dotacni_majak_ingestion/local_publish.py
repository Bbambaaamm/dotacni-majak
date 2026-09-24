from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9._:-]+")


def stable_id(*parts: str) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        raise ValueError("stable_id requires at least one non-empty part")
    return ":".join(cleaned)


def slugify(value: str) -> str:
    lowered = value.casefold()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered.encode("ascii", "ignore").decode())
    cleaned = normalized.strip("-")
    if cleaned:
        return cleaned[:180]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def sql_text(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def sql_int(value: int | None) -> str:
    return "NULL" if value is None else str(int(value))


@dataclass(frozen=True, slots=True)
class SearchableGrant:
    source_id: str
    source_code: str
    source_name: str
    source_base_url: str
    adapter_key: str
    source_external_id: str
    source_url: str
    content_hash: str

    provider_id: str
    provider_name: str
    provider_type: str

    programme_id: str
    programme_name: str
    funding_origin: str

    grant_call_id: str
    grant_version_id: str
    canonical_slug: str

    title: str
    summary: str
    status: str
    verification_status: str

    captured_at: str
    published_at: str | None = None
    submission_open_at: str | None = None
    submission_close_at: str | None = None

    supported_activities: str = ""
    eligible_costs: str = ""
    keywords: str = ""
    retrieval_mode: str = "HTML"
    currency_code: str = "CZK"

    def validate(self) -> None:
        if self.status not in {
            "DRAFT",
            "ANNOUNCED",
            "PLANNED",
            "OPEN",
            "PAUSED",
            "CLOSED",
            "CANCELLED",
            "ARCHIVED",
        }:
            raise ValueError(f"unsupported canonical status {self.status!r}")
        if self.verification_status not in {
            "AUTO_EXTRACTED",
            "PARTIALLY_VERIFIED",
            "VERIFIED",
            "NEEDS_REVIEW",
        }:
            raise ValueError(
                f"unsupported verification status {self.verification_status!r}"
            )
        if not re.fullmatch(r"[a-f0-9]{64}", self.content_hash):
            raise ValueError("content_hash must be lowercase SHA-256 hex")
        if self.retrieval_mode not in {
            "API", "JSON", "XML", "RSS", "CSV", "XLSX", "HTML", "PDF", "DOCX"
        }:
            raise ValueError(f"unsupported retrieval_mode {self.retrieval_mode!r}")
        if not re.fullmatch(r"[A-Z]{3}", self.currency_code):
            raise ValueError("currency_code must be an ISO-4217-like 3-letter code")


def _grant_sql(grant: SearchableGrant, run_id: str) -> list[str]:
    grant.validate()

    provider = f"""INSERT INTO providers(
      id,name,provider_type,official_url
    ) VALUES (
      {sql_text(grant.provider_id)},
      {sql_text(grant.provider_name)},
      {sql_text(grant.provider_type)},
      {sql_text(grant.source_base_url)}
    )
    ON CONFLICT(id) DO UPDATE SET
      name=excluded.name,
      provider_type=excluded.provider_type,
      official_url=excluded.official_url;"""

    programme = f"""INSERT INTO programmes(
      id,provider_id,name,funding_origin,official_url
    ) VALUES (
      {sql_text(grant.programme_id)},
      {sql_text(grant.provider_id)},
      {sql_text(grant.programme_name)},
      {sql_text(grant.funding_origin)},
      {sql_text(grant.source_base_url)}
    )
    ON CONFLICT(id) DO UPDATE SET
      name=excluded.name,
      funding_origin=excluded.funding_origin,
      official_url=excluded.official_url;"""

    source = f"""INSERT INTO source_registry(
      id,code,name,base_url,adapter_key,authority,retrieval_mode,
      refresh_minutes,enabled,priority
    ) VALUES (
      {sql_text(grant.source_id)},
      {sql_text(grant.source_code)},
      {sql_text(grant.source_name)},
      {sql_text(grant.source_base_url)},
      {sql_text(grant.adapter_key)},
      'OFFICIAL',
      {sql_text(grant.retrieval_mode)},
      360,
      1,
      10
    )
    ON CONFLICT(id) DO UPDATE SET
      name=excluded.name,
      base_url=excluded.base_url,
      adapter_key=excluded.adapter_key,
      enabled=1;"""

    call = f"""INSERT INTO grant_calls(
      id,programme_id,canonical_code,canonical_slug,current_version_id,
      current_status,current_title,first_seen_at,first_published_at,
      created_at,updated_at
    ) VALUES (
      {sql_text(grant.grant_call_id)},
      {sql_text(grant.programme_id)},
      {sql_text(grant.source_external_id)},
      {sql_text(grant.canonical_slug)},
      NULL,
      {sql_text(grant.status)},
      {sql_text(grant.title)},
      {sql_text(grant.captured_at)},
      {sql_text(grant.published_at)},
      {sql_text(grant.captured_at)},
      {sql_text(grant.captured_at)}
    )
    ON CONFLICT(id) DO UPDATE SET
      programme_id=excluded.programme_id,
      canonical_code=excluded.canonical_code,
      current_status=excluded.current_status,
      current_title=excluded.current_title,
      updated_at=excluded.updated_at;"""

    version = f"""INSERT OR IGNORE INTO grant_call_versions(
      id,grant_call_id,version_number,captured_at,effective_from,effective_to,
      title,summary,status,published_at,submission_open_at,submission_close_at,
      application_url,official_detail_url,currency_code,normalization_version,
      content_hash,verification_status,created_at
    ) VALUES (
      {sql_text(grant.grant_version_id)},
      {sql_text(grant.grant_call_id)},
      (
        SELECT COALESCE(MAX(version_number),0)+1
        FROM grant_call_versions
        WHERE grant_call_id={sql_text(grant.grant_call_id)}
      ),
      {sql_text(grant.captured_at)},
      NULL,
      NULL,
      {sql_text(grant.title)},
      {sql_text(grant.summary)},
      {sql_text(grant.status)},
      {sql_text(grant.published_at)},
      {sql_text(grant.submission_open_at)},
      {sql_text(grant.submission_close_at)},
      NULL,
      {sql_text(grant.source_url)},
      {sql_text(grant.currency_code)},
      'local-publisher-v2',
      {sql_text(grant.content_hash)},
      {sql_text(grant.verification_status)},
      {sql_text(grant.captured_at)}
    );"""

    current_version = f"""UPDATE grant_calls
    SET
      current_version_id={sql_text(grant.grant_version_id)},
      current_status={sql_text(grant.status)},
      current_title={sql_text(grant.title)},
      updated_at={sql_text(grant.captured_at)}
    WHERE id={sql_text(grant.grant_call_id)};"""

    source_record = f"""INSERT INTO source_records(
      id,source_id,external_id,canonical_url,record_type,grant_call_id,
      first_seen_at,last_seen_at,presence_state,missing_run_count,content_hash
    ) VALUES (
      {sql_text(stable_id(grant.source_id, grant.source_external_id))},
      {sql_text(grant.source_id)},
      {sql_text(grant.source_external_id)},
      {sql_text(grant.source_url)},
      'GRANT_CALL',
      {sql_text(grant.grant_call_id)},
      {sql_text(grant.captured_at)},
      {sql_text(grant.captured_at)},
      'SEEN',
      0,
      {sql_text(grant.content_hash)}
    )
    ON CONFLICT(id) DO UPDATE SET
      canonical_url=excluded.canonical_url,
      grant_call_id=excluded.grant_call_id,
      last_seen_at=excluded.last_seen_at,
      presence_state='SEEN',
      missing_run_count=0,
      content_hash=excluded.content_hash;"""

    # Only the current version is searchable. Historical GrantCallVersion rows
    # remain immutable and auditable in canonical storage.
    remove_old_search = f"""DELETE FROM grant_search_documents
    WHERE grant_call_version_id IN (
      SELECT id FROM grant_call_versions
      WHERE grant_call_id={sql_text(grant.grant_call_id)}
        AND id<>{sql_text(grant.grant_version_id)}
    );"""

    search = f"""INSERT INTO grant_search_documents(
      grant_call_version_id,title,summary,supported_activities,
      eligible_costs,keywords,status,submission_close_at,updated_at
    ) VALUES (
      {sql_text(grant.grant_version_id)},
      {sql_text(grant.title)},
      {sql_text(grant.summary)},
      {sql_text(grant.supported_activities)},
      {sql_text(grant.eligible_costs)},
      {sql_text(grant.keywords)},
      {sql_text(grant.status)},
      {sql_text(grant.submission_close_at)},
      {sql_text(grant.captured_at)}
    )
    ON CONFLICT(grant_call_version_id) DO UPDATE SET
      title=excluded.title,
      summary=excluded.summary,
      supported_activities=excluded.supported_activities,
      eligible_costs=excluded.eligible_costs,
      keywords=excluded.keywords,
      status=excluded.status,
      submission_close_at=excluded.submission_close_at,
      updated_at=excluded.updated_at;"""

    return [
        provider,
        programme,
        source,
        call,
        version,
        current_version,
        source_record,
        remove_old_search,
        search,
    ]


def render_import_sql(
    grants: Iterable[SearchableGrant],
    *,
    source_id: str,
    source_code: str,
    source_name: str,
    adapter_version: str,
    captured_at: str | None = None,
) -> str:
    rows = list(grants)
    if not rows:
        raise ValueError("refusing to publish an empty source run")

    now = captured_at or datetime.now(timezone.utc).isoformat()
    run_id = stable_id("local-run", source_code, hashlib.sha256(now.encode()).hexdigest()[:16])

    statements = [
        "PRAGMA foreign_keys = ON;",
        "BEGIN IMMEDIATE;",
        f"""INSERT OR IGNORE INTO source_runs(
          id,source_id,started_at,finished_at,status,records_seen,
          new_records,changed_records,error_count,adapter_version
        ) VALUES (
          {sql_text(run_id)},
          {sql_text(source_id)},
          {sql_text(now)},
          {sql_text(now)},
          'COMPLETED',
          {len(rows)},
          0,
          0,
          0,
          {sql_text(adapter_version)}
        );""",
    ]

    # source_registry is created by the first grant before source_runs can
    # reference it. Reorder the first source statement before the run insert.
    first_sql = _grant_sql(rows[0], run_id)
    source_stmt = first_sql.pop(2)
    statements.insert(2, source_stmt)

    # Source run can now safely reference source_registry.
    run_stmt = statements.pop(3)
    statements.append(run_stmt)

    statements.extend(first_sql)
    for grant in rows[1:]:
        statements.extend(_grant_sql(grant, run_id))

    statements.extend(
        [
            "COMMIT;",
            f"-- imported {len(rows)} grant records from {source_name}",
        ]
    )
    return "\n\n".join(statements) + "\n"
