from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "eu-funding" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_eu_funding import EuFundingTendersAdapter
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import (
    AdapterContext,
    GuardedHttpClient,
    HealthStatus,
)


async def main() -> None:
    adapter = EuFundingTendersAdapter(page_size=5)

    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            allowed_post_paths=set(adapter.descriptor.allowed_post_paths),
            requests_per_second=0.5,
            max_concurrency=1,
            max_response_bytes=20 * 1024 * 1024,
            max_request_body_bytes=64 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )

            health = await adapter.healthcheck(ctx)
            print(f"HEALTH={health.status.value}")
            if health.status != HealthStatus.HEALTHY:
                raise SystemExit(f"EU source health is {health.status}: {health.detail}")

            page = await adapter.discover(ctx, None)
            print(f"TOTAL_HINT={page.total_hint}")
            print(f"DISCOVERED_CURRENT={len(page.items)}")
            if not page.items:
                raise SystemExit("No current EU grant topics discovered on first page")

            item = page.items[0]
            print(f"FIRST_IDENTIFIER={item.external_id}")
            print(f"FIRST_STATUS={item.native_status_hint}")
            print(f"FIRST_DEADLINE={item.metadata.get('deadline')}")

            result = await adapter.fetch_record(ctx, item)
            if result.record is None:
                raise SystemExit("Topic detail returned no NativeRecord")

            print(f"DETAIL_STATE={result.state.value}")
            print(f"RAW_SNAPSHOTS={len(result.record.snapshot_ids)}")
            print(f"ARTIFACTS={len(result.record.artifacts)}")
            print(f"TITLE={result.record.native_title}")

            if not result.record.snapshot_ids:
                raise SystemExit("RAW-first invariant failed: no snapshot id")


if __name__ == "__main__":
    asyncio.run(main())
