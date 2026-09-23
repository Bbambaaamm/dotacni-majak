from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_praha import PrahaAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = PrahaAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="praha-live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )
            health = await adapter.healthcheck(ctx)
            page = await adapter.discover(ctx, None)
            print("health", health.status.value, health.detail)
            print("discovered", page.total_hint)
            if not page.items:
                raise SystemExit("Prague live smoke discovered zero grant calls")
            first = page.items[0]
            result = await adapter.fetch_record(ctx, first)
            if result.record is None or not result.record.snapshot_ids:
                raise SystemExit("Prague live smoke detail has no RAW-backed record")
            print(
                "sample",
                result.record.external_id,
                result.record.native_status,
                result.record.native_title,
                len(result.record.artifacts),
            )


if __name__ == "__main__":
    asyncio.run(main())
