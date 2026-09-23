from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_liberecky import LibereckyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = LibereckyAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="liberecky-live-smoke",
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
            if health.status.value != "HEALTHY":
                raise SystemExit(f"Liberecký source is not healthy: {health.detail}")
            if not page.items:
                raise SystemExit("Liberecký live smoke discovered zero programmes")

            first = page.items[0]
            record = (await adapter.fetch_record(ctx, first)).record
            if record is None or not record.snapshot_ids:
                raise SystemExit("Liberecký detail did not produce RAW-backed record")
            print(
                "sample",
                record.external_id,
                record.native_status,
                record.native_title,
                record.raw_fields.get("submissionOpenAt"),
                record.raw_fields.get("submissionCloseAt"),
                len(record.artifacts),
            )


if __name__ == "__main__":
    asyncio.run(main())
