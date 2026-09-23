from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "nsa" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.local_publish import (
    SearchableGrant,
    render_import_sql,
    slugify,
    stable_id,
)
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_nsa import NsaAdapter
from dotacni_majak_source_sdk import (
    AdapterContext,
    FetchState,
    GuardedHttpClient,
    HealthStatus,
)


ACTIVE_CANONICAL = {"OPEN", "PLANNED", "CLOSED"}


def programme_from_item(item) -> tuple[str, str]:
    listing_url = str(item.metadata.get("listing_url") or "")
    if "dotace-investicni-parasport" in listing_url:
        return "programme:nsa:parasport", "NSA — Parasport"
    if "dotace-neinvesticni-parasport" in listing_url:
        return "programme:nsa:parasport", "NSA — Neinvestiční parasport"
    if "dotace-investicni" in listing_url:
        return "programme:nsa:investment", "NSA — Investiční výzvy"
    return "programme:nsa:noninvestment", "NSA — Neinvestiční výzvy"


def canonical_status(native_status: str | None, *, published: bool) -> str:
    value = (native_status or "").upper()
    if value in ACTIVE_CANONICAL:
        return value
    # Native UNKNOWN means that the adapter does not have enough information
    # to claim OPEN/CLOSED/ANNOUNCED. Keep it out of default search.
    return "DRAFT"


def content_hash_from_record(record) -> str:
    if record.snapshot_ids:
        candidate = record.snapshot_ids[0].rsplit(":", 1)[-1]
        if len(candidate) == 64 and all(ch in "0123456789abcdef" for ch in candidate):
            return candidate
    payload = record.model_dump_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def to_searchable(item, record, captured_at: datetime) -> SearchableGrant:
    programme_id, programme_name = programme_from_item(item)
    external_id = record.external_id
    content_hash = content_hash_from_record(record)
    grant_call_id = stable_id("grant", "nsa", external_id.replace("/", "-"))
    version_id = stable_id(grant_call_id, "sha", content_hash[:24])
    description = str(record.raw_fields.get("descriptionText") or "").strip()
    call_type = str(record.raw_fields.get("callType") or "").strip()
    title = (record.native_title or item.title_hint or external_id).strip()
    status = canonical_status(
        record.native_status,
        published=record.published_at is not None,
    )

    return SearchableGrant(
        source_id="source:nsa",
        source_code="NSA",
        source_name="Národní sportovní agentura",
        source_base_url="https://nsa.gov.cz/",
        adapter_key="nsa-cz",
        source_external_id=external_id,
        source_url=str(record.detail_url),
        content_hash=content_hash,
        provider_id="provider:nsa",
        provider_name="Národní sportovní agentura",
        provider_type="NATIONAL",
        programme_id=programme_id,
        programme_name=programme_name,
        funding_origin="CZ_NATIONAL",
        grant_call_id=grant_call_id,
        grant_version_id=version_id,
        canonical_slug=slugify(f"nsa-{external_id}"),
        title=title,
        summary=description[:4000],
        status=status,
        verification_status="PARTIALLY_VERIFIED",
        captured_at=captured_at.isoformat(),
        published_at=record.published_at.isoformat() if record.published_at else None,
        submission_open_at=record.raw_fields.get("submissionOpenAt"),
        submission_close_at=record.raw_fields.get("submissionCloseAt"),
        supported_activities=description,
        eligible_costs="",
        keywords=" ".join(
            part
            for part in (call_type, external_id, "Národní sportovní agentura")
            if part
        ),
    )


async def collect(limit: int | None, raw_dir: Path) -> tuple[list[SearchableGrant], list[str]]:
    adapter = NsaAdapter()
    captured_at = datetime.now(timezone.utc)
    raw_dir.mkdir(parents=True, exist_ok=True)

    async with GuardedHttpClient(
        allowed_hosts=set(adapter.descriptor.allowed_hosts),
        requests_per_second=adapter.descriptor.requests_per_second,
        max_concurrency=adapter.descriptor.max_concurrency,
        timeout_seconds=30,
        max_response_bytes=25 * 1024 * 1024,
    ) as client:
        ctx = AdapterContext(
            run_id=f"local-nsa-{captured_at:%Y%m%dT%H%M%SZ}",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(raw_dir),
            now=captured_at,
        )

        health = await adapter.healthcheck(ctx)
        if health.status == HealthStatus.UNAVAILABLE:
            raise RuntimeError(f"NSA source unavailable: {health.detail or 'unknown error'}")

        page = await adapter.discover(ctx, None)
        if not page.items:
            raise RuntimeError("NSA discovery returned zero records; refusing empty publish")

        items = page.items[:limit] if limit else page.items
        grants: list[SearchableGrant] = []
        failures: list[str] = []

        for index, item in enumerate(items, start=1):
            print(f"[NSA {index}/{len(items)}] {item.external_id} {item.title_hint or ''}")
            try:
                result = await adapter.fetch_record(ctx, item)
                if result.state == FetchState.GONE:
                    failures.append(f"{item.external_id}: detail is gone")
                    continue
                if result.record is None:
                    failures.append(f"{item.external_id}: no record returned")
                    continue
                grants.append(to_searchable(item, result.record, captured_at))
            except Exception as exc:
                failures.append(f"{item.external_id}: {type(exc).__name__}: {exc}")

        if not grants:
            raise RuntimeError(
                "NSA refresh produced zero usable records; refusing to replace local data"
            )

        return grants, failures


async def async_main(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    raw_dir = Path(args.raw_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    grants, failures = await collect(args.limit, raw_dir)
    sql = render_import_sql(
        grants,
        source_id="source:nsa",
        source_code="NSA",
        source_name="Národní sportovní agentura",
        adapter_version=NsaAdapter.descriptor.adapter_version,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    output.write_text(sql, encoding="utf-8")

    print(f"SQL={output}")
    print(f"GRANTS={len(grants)}")
    print(f"FAILURES={len(failures)}")
    for failure in failures:
        print(f"WARNING={failure}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch current NSA calls and produce idempotent local D1 import SQL."
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".local" / "nsa-import.sql"),
    )
    parser.add_argument(
        "--raw-dir",
        default=str(ROOT / ".local" / "raw"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Development-only cap on discovered records. Default: all.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
