from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "dotaceeu" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_dotaceeu import DotaceEuAdapter
from dotacni_majak_ingestion.collection import collect_searchable_grants
from dotacni_majak_ingestion.normalization import (
    DotaceEuGrantNormalizer,
    canonical_status as _canonical_status,
)
from dotacni_majak_source_sdk import DiscoveryItem
from local_trusted_publish import publish_grants_to_local_d1


_NORMALIZER = DotaceEuGrantNormalizer()


def canonical_status(native_status: str | None) -> str:
    return _canonical_status(native_status)


def programme_identity(record):
    item = DiscoveryItem(
        external_id=record.external_id,
        detail_url=record.detail_url,
        title_hint=record.native_title,
    )
    return _NORMALIZER.programme_identity(item, record)


def to_searchable(record, captured_at: datetime):
    item = DiscoveryItem(
        external_id=record.external_id,
        detail_url=record.detail_url,
        title_hint=record.native_title,
    )
    return _NORMALIZER.normalize(item, record, captured_at)


async def collect(*, limit: int | None, raw_dir: Path):
    result = await collect_searchable_grants(
        adapter=DotaceEuAdapter(),
        normalizer=_NORMALIZER,
        raw_dir=raw_dir,
        limit=limit,
        timeout_seconds=45,
        max_response_bytes=30 * 1024 * 1024,
    )
    return list(result.grants), list(result.failures)


async def async_main(args: argparse.Namespace) -> None:
    raw_dir = Path(args.raw_dir).resolve()
    grants, failures = await collect(limit=args.limit, raw_dir=raw_dir)
    summary = publish_grants_to_local_d1(
        grants,
        raw_dir=raw_dir,
        persist_root=Path(args.db_root).resolve(),
        adapter_version=DotaceEuAdapter.descriptor.adapter_version,
        now=datetime.now(timezone.utc),
    )

    print(f"DB={summary.database_path}")
    print(f"GRANTS={summary.grants}")
    print(f"SEARCH_EVENTS={summary.search_events_delivered}")
    print(f"FAILURES={len(failures)}")
    for failure in failures:
        print(f"WARNING={failure}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch current DotaceEU calls and publish through the trusted local D1 pipeline."
        )
    )
    parser.add_argument(
        "--db-root",
        default=str(ROOT / ".wrangler" / "local"),
        help="Wrangler --persist-to root containing the migrated local D1 database.",
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
