from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "msmt" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_msmt import MsmtAdapter, OpJakAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def probe(adapter) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
        ) as client:
            ctx = AdapterContext(
                run_id=f"{adapter.descriptor.code.lower()}-live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )
            health = await adapter.healthcheck(ctx)
            print(adapter.descriptor.code, "health", health.status.value, health.detail or "")
            page = await adapter.discover(ctx, None)
            print(adapter.descriptor.code, "discovered", page.total_hint)
            if not page.items:
                raise SystemExit(f"{adapter.descriptor.code} discovered zero calls")
            record = (await adapter.fetch_record(ctx, page.items[0])).record
            if record is None:
                raise SystemExit(f"{adapter.descriptor.code} detail returned no record")
            print(adapter.descriptor.code, "sample", record.external_id, record.native_status)


async def main() -> None:
    await probe(MsmtAdapter())
    await probe(OpJakAdapter())


if __name__ == "__main__":
    asyncio.run(main())
