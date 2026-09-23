from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_jihocesky import JihoceskyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = JihoceskyAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="jihocesky-live-smoke",
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
                raise SystemExit(f"Jihočeský source is not healthy: {health.detail}")
            if not page.items:
                raise SystemExit("Jihočeský live smoke discovered zero calls")

            first = page.items[0]
            result = await adapter.fetch_record(ctx, first)
            record = result.record
            if record is None or not record.snapshot_ids:
                raise SystemExit("Jihočeský record is not RAW-backed")
            if record.raw_fields.get("regionCode") != "CZ031":
                raise SystemExit("Jihočeský record has wrong region code")
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
