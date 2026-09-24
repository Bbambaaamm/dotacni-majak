from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "nsa" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.collection import collect_searchable_grants
from dotacni_majak_ingestion.local_publish import render_import_sql
from dotacni_majak_ingestion.normalization import (
    NsaGrantNormalizer,
    canonical_status as _canonical_status,
    record_content_hash,
)
from dotacni_majak_nsa import NsaAdapter


_NORMALIZER = NsaGrantNormalizer()


def canonical_status(native_status: str | None, *, published: bool = False) -> str:
    del published
    return _canonical_status(native_status)


def content_hash_from_record(record) -> str:
    return record_content_hash(record)


def to_searchable(item, record, captured_at: datetime):
    return _NORMALIZER.normalize(item, record, captured_at)


async def collect(limit: int | None, raw_dir: Path):
    result = await collect_searchable_grants(
        adapter=NsaAdapter(),
        normalizer=_NORMALIZER,
        raw_dir=raw_dir,
        limit=limit,
        timeout_seconds=30,
        max_response_bytes=25 * 1024 * 1024,
    )
    return list(result.grants), list(result.failures)


async def async_main(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    raw_dir = Path(args.raw_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    grants, failures = await collect(args.limit, raw_dir)
    captured_at = datetime.now(timezone.utc).isoformat()
    sql = render_import_sql(
        grants,
        source_id="source:nsa",
        source_code="NSA",
        source_name="Národní sportovní agentura",
        adapter_version=NsaAdapter.descriptor.adapter_version,
        captured_at=captured_at,
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
