from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "eu-funding" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_eu_funding import EuFundingTendersAdapter
from dotacni_majak_ingestion.collection import collect_searchable_grants
from dotacni_majak_ingestion.local_publish import render_import_sql
from dotacni_majak_ingestion.normalization import EuFundingGrantNormalizer


_NORMALIZER = EuFundingGrantNormalizer()


async def collect(*, limit: int | None, raw_dir: Path):
    result = await collect_searchable_grants(
        adapter=EuFundingTendersAdapter(page_size=100),
        normalizer=_NORMALIZER,
        raw_dir=raw_dir,
        limit=limit,
        timeout_seconds=60,
        max_response_bytes=30 * 1024 * 1024,
    )
    return list(result.grants), list(result.failures), result.pages


async def async_main(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    raw_dir = Path(args.raw_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    grants, failures, pages = await collect(limit=args.limit, raw_dir=raw_dir)
    sql = render_import_sql(
        grants,
        source_id="source:eu-ft",
        source_code="EU_FT",
        source_name="EU Funding & Tenders Portal",
        adapter_version=EuFundingTendersAdapter.descriptor.adapter_version,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    output.write_text(sql, encoding="utf-8")

    print(f"SQL={output}")
    print(f"GRANTS={len(grants)}")
    print(f"PAGES={pages}")
    print(f"FAILURES={len(failures)}")
    for failure in failures:
        print(f"WARNING={failure}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch current EU Funding & Tenders opportunities and produce "
            "idempotent local D1 import SQL."
        )
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".local" / "eu-funding-import.sql"),
    )
    parser.add_argument(
        "--raw-dir",
        default=str(ROOT / ".local" / "raw"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Optional development cap on normalized opportunities. "
            "Default: all discovered active/planned records."
        ),
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
