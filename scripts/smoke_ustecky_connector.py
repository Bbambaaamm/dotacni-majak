from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient
from dotacni_majak_ustecky import UsteckyAdapter


async def main() -> None:
    adapter = UsteckyAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="ustecky-live-smoke",
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
                raise SystemExit(f"Ústecký source is not healthy: {health.detail}")
            if not page.items:
                raise SystemExit("Ústecký live smoke discovered zero grant articles")

            # Find a record whose detail validates as a structured grant page.
            sample = None
            for item in page.items[:20]:
                result = await adapter.fetch_record(ctx, item)
                record = result.record
                if record and record.raw_fields.get("sourceCallCode"):
                    sample = record
                    break

            if sample is None:
                raise SystemExit("Ústecký live smoke found no structured grant detail among first 20 items")
            if not sample.snapshot_ids:
                raise SystemExit("Ústecký sample record is not RAW-backed")
            print(
                "sample",
                sample.external_id,
                sample.raw_fields.get("sourceCallCode"),
                sample.native_status,
                sample.native_title,
                sample.raw_fields.get("submissionOpenAt"),
                sample.raw_fields.get("submissionCloseAt"),
                len(sample.artifacts),
            )


if __name__ == "__main__":
    asyncio.run(main())
