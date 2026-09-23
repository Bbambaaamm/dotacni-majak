from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_jdp import JdpAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = JdpAdapter(page_size=8)
    async with GuardedHttpClient(
        allowed_hosts=set(adapter.descriptor.allowed_hosts),
        allowed_post_paths=set(adapter.descriptor.allowed_post_paths),
        requests_per_second=adapter.descriptor.requests_per_second,
        max_concurrency=adapter.descriptor.max_concurrency,
        max_response_bytes=10 * 1024 * 1024,
    ) as client:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="jdp-live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )
            health = await adapter.healthcheck(ctx)
            print("health", health.status.value, health.detail)
            if health.status.value != "HEALTHY":
                raise SystemExit(f"JDP source unhealthy: {health.detail}")

            page = await adapter.discover(ctx, None)
            print("discovered", len(page.items), "total", page.total_hint)
            if not page.items:
                raise SystemExit("JDP public dashboard discovered zero open calls")

            record = (await adapter.fetch_record(ctx, page.items[0])).record
            if record is None or not record.snapshot_ids:
                raise SystemExit("JDP record is not RAW-backed")
            print(
                "sample",
                record.external_id,
                record.native_status,
                record.native_title,
                record.raw_fields.get("submissionCloseAtSource"),
                record.raw_fields.get("grantAmountMaxSource"),
            )


if __name__ == "__main__":
    asyncio.run(main())
