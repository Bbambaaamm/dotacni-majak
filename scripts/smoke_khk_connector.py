#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_khk import KhkAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = KhkAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            allowed_post_paths=set(adapter.descriptor.allowed_post_paths),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
        ) as http:
            ctx = AdapterContext(
                run_id="khk-live-smoke",
                http=http,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )
            health = await adapter.healthcheck(ctx)
            if health.status.value == "UNAVAILABLE":
                raise RuntimeError(f"KHK health unavailable: {health.detail}")
            page = await adapter.discover(ctx, None)
            if not page.items:
                raise RuntimeError("KHK discovery returned zero public programmes")
            record = (await adapter.fetch_record(ctx, page.items[0])).record
            if record is None:
                raise RuntimeError("KHK first record did not materialize")
            print(
                {
                    "health": health.status.value,
                    "programmes": page.total_hint,
                    "first": record.external_id,
                    "documents": len(record.raw_fields.get("documents", [])),
                    "documentCoverage": record.raw_fields.get("documentCoverage"),
                }
            )


if __name__ == "__main__":
    asyncio.run(main())
