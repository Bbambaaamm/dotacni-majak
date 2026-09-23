from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "mpsv" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_mpsv import MpsvAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = MpsvAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
        ) as client:
            ctx = AdapterContext(
                run_id="mpsv-live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )
            health = await adapter.healthcheck(ctx)
            print("health", health.status.value, health.detail or "")
            page = await adapter.discover(ctx, None)
            print("discovered", page.total_hint)
            if not page.items:
                raise SystemExit("MPSV live smoke discovered zero calls")
            record = (await adapter.fetch_record(ctx, page.items[0])).record
            if record is None:
                raise SystemExit("MPSV detail returned no record")
            print(
                "sample",
                record.external_id,
                record.native_status,
                record.raw_fields.get("programme"),
            )


if __name__ == "__main__":
    asyncio.run(main())
