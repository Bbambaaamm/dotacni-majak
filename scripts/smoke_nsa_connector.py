from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "nsa" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_nsa import NsaAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient, HealthStatus


async def main() -> None:
    adapter = NsaAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=0.5,
            max_concurrency=1,
            timeout_seconds=30,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="nsa-live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )

            health = await adapter.healthcheck(ctx)
            print(f"HEALTH={health.status.value}")
            if health.status != HealthStatus.HEALTHY:
                raise SystemExit(f"NSA health is {health.status.value}: {health.detail}")

            page = await adapter.discover(ctx, None)
            print(f"DISCOVERED={len(page.items)}")
            if not page.items:
                raise SystemExit("No NSA calls discovered")

            target = next((item for item in page.items if item.external_id == "16/2026"), page.items[0])
            print(f"TARGET={target.external_id}")
            result = await adapter.fetch_record(ctx, target)
            if result.record is None:
                raise SystemExit("NSA detail returned no NativeRecord")
            print(f"STATUS={result.record.native_status}")
            print(f"TITLE={result.record.native_title}")
            print(f"ALLOCATION_CZK={result.record.raw_fields.get('allocationCzk')}")
            print(f"ARTIFACTS={len(result.record.artifacts)}")
            print(f"RAW_SNAPSHOTS={len(result.record.snapshot_ids)}")
            if not result.record.snapshot_ids:
                raise SystemExit("RAW-first invariant failed")


if __name__ == "__main__":
    asyncio.run(main())
