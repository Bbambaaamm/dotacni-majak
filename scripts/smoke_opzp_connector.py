from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "opzp" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_opzp import OpzpAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = OpzpAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="opzp-live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )

            health = await adapter.healthcheck(ctx)
            if health.status.value == "UNAVAILABLE":
                raise SystemExit(f"OPŽP unavailable: {health.detail}")

            page = await adapter.discover(ctx, None)
            if not page.items:
                raise SystemExit("OPŽP discovery returned no calls")

            result = await adapter.fetch_record(ctx, page.items[0])
            if result.record is None or not result.record.snapshot_ids:
                raise SystemExit("OPŽP detail did not produce RAW-backed record")

            print(
                "OPŽP live smoke OK:",
                health.status.value,
                len(page.items),
                result.record.external_id,
                result.record.native_status,
            )


if __name__ == "__main__":
    asyncio.run(main())
