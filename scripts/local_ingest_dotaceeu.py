from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "dotaceeu" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_dotaceeu import DotaceEuAdapter
from dotacni_majak_ingestion.local_publish import (
    SearchableGrant,
    render_import_sql,
    slugify,
    stable_id,
)
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import (
    AdapterContext,
    FetchState,
    GuardedHttpClient,
    HealthStatus,
)


CANONICAL_STATUSES = {
    "OPEN",
    "PLANNED",
    "PAUSED",
    "CLOSED",
    "CANCELLED",
}


def canonical_status(native_status: str | None) -> str:
    value = (native_status or "").upper()
    return value if value in CANONICAL_STATUSES else "DRAFT"


def snapshot_hash(record) -> str:
    if record.snapshot_ids:
        candidate = record.snapshot_ids[0].rsplit(":", 1)[-1]
        if len(candidate) == 64 and all(ch in "0123456789abcdef" for ch in candidate):
            return candidate
    return hashlib.sha256(record.model_dump_json().encode("utf-8")).hexdigest()


def programme_identity(record) -> tuple[str, str]:
    name = str(record.raw_fields.get("programme") or "").strip()
    if not name:
        name = "DotaceEU — program neuveden"
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return stable_id("programme", "dotaceeu", digest), name


def to_searchable(record, captured_at: datetime) -> SearchableGrant:
    programme_id, programme_name = programme_identity(record)
    content_hash = snapshot_hash(record)
    external_id = record.external_id
    grant_call_id = stable_id("grant", "dotaceeu", external_id)
    version_id = stable_id(grant_call_id, "sha", content_hash[:24])

    call_type = str(record.raw_fields.get("callType") or "").strip()
    priority = str(record.raw_fields.get("priorityAxis") or "").strip()
    applicants = str(record.raw_fields.get("eligibleApplicantsText") or "").strip()
    period = str(record.raw_fields.get("programmingPeriod") or "").strip()
    call_code = str(record.raw_fields.get("callCode") or "").strip()

    summary_parts = [
        f"Program: {programme_name}" if programme_name else "",
        f"Priorita: {priority}" if priority else "",
        f"Typ výzvy: {call_type}" if call_type else "",
        f"Oprávnění žadatelé: {applicants}" if applicants else "",
    ]
    summary = " · ".join(part for part in summary_parts if part)

    # DotaceEU is a discovery source. It often does not carry a normalized
    # supported-activities field, so search text is limited to what the
    # official detail actually states instead of inventing activities.
    searchable_context = " ".join(
        part
        for part in (
            record.native_title or "",
            programme_name,
            priority,
            call_type,
            applicants,
        )
        if part
    )

    return SearchableGrant(
        source_id="source:dotaceeu",
        source_code="DOTACEEU",
        source_name="DotaceEU.cz",
        source_base_url="https://www.dotaceeu.cz/",
        adapter_key="dotaceeu-cz",
        source_external_id=external_id,
        source_url=str(record.detail_url),
        content_hash=content_hash,
        provider_id="provider:dotaceeu:unspecified",
        provider_name="Poskytovatel neuveden v agregovaném záznamu",
        provider_type="NATIONAL",
        programme_id=programme_id,
        programme_name=programme_name,
        funding_origin="EU_SHARED",
        grant_call_id=grant_call_id,
        grant_version_id=version_id,
        canonical_slug=slugify(f"dotaceeu-{external_id}"),
        title=(record.native_title or external_id).strip(),
        summary=summary[:4000],
        status=canonical_status(record.native_status),
        verification_status="PARTIALLY_VERIFIED",
        captured_at=captured_at.isoformat(),
        submission_open_at=record.raw_fields.get("submissionOpenAt"),
        submission_close_at=record.raw_fields.get("submissionCloseAt"),
        supported_activities=searchable_context,
        eligible_costs="",
        keywords=" ".join(
            part for part in (call_code, call_type, period, programme_name) if part
        ),
    )


async def collect(
    *,
    limit: int | None,
    raw_dir: Path,
) -> tuple[list[SearchableGrant], list[str]]:
    adapter = DotaceEuAdapter()
    captured_at = datetime.now(timezone.utc)
    raw_dir.mkdir(parents=True, exist_ok=True)

    async with GuardedHttpClient(
        allowed_hosts=set(adapter.descriptor.allowed_hosts),
        requests_per_second=adapter.descriptor.requests_per_second,
        max_concurrency=adapter.descriptor.max_concurrency,
        timeout_seconds=45,
        max_response_bytes=30 * 1024 * 1024,
    ) as client:
        ctx = AdapterContext(
            run_id=f"local-dotaceeu-{captured_at:%Y%m%dT%H%M%SZ}",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(raw_dir),
            now=captured_at,
        )

        health = await adapter.healthcheck(ctx)
        if health.status == HealthStatus.UNAVAILABLE:
            raise RuntimeError(
                f"DotaceEU source unavailable: {health.detail or 'unknown error'}"
            )

        page = await adapter.discover(ctx, None)
        if not page.items:
            raise RuntimeError(
                "DotaceEU discovery returned zero records; refusing empty publish"
            )

        items = page.items[:limit] if limit else page.items
        grants: list[SearchableGrant] = []
        failures: list[str] = []

        for index, item in enumerate(items, start=1):
            print(
                f"[DotaceEU {index}/{len(items)}] "
                f"{item.external_id} {item.title_hint or ''}"
            )
            try:
                result = await adapter.fetch_record(ctx, item)
                if result.state == FetchState.GONE:
                    failures.append(f"{item.external_id}: detail is gone")
                    continue
                if result.record is None:
                    failures.append(f"{item.external_id}: no record returned")
                    continue
                grants.append(to_searchable(result.record, captured_at))
            except Exception as exc:
                failures.append(
                    f"{item.external_id}: {type(exc).__name__}: {exc}"
                )

        if not grants:
            raise RuntimeError(
                "DotaceEU refresh produced zero usable records; "
                "refusing to replace local data"
            )

        return grants, failures


async def async_main(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    raw_dir = Path(args.raw_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    grants, failures = await collect(limit=args.limit, raw_dir=raw_dir)
    sql = render_import_sql(
        grants,
        source_id="source:dotaceeu",
        source_code="DOTACEEU",
        source_name="DotaceEU.cz",
        adapter_version=DotaceEuAdapter.descriptor.adapter_version,
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
        description=(
            "Fetch current DotaceEU calls and produce idempotent local D1 import SQL."
        )
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".local" / "dotaceeu-import.sql"),
    )
    parser.add_argument(
        "--raw-dir",
        default=str(ROOT / ".local" / "raw"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Development-only cap. Default: all discovered calls.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
