#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient
from dotacni_majak_stredocesky import StredoceskyAdapter


async def main() -> None:
    adapter = StredoceskyAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
        ) as http:
            ctx = AdapterContext(
                run_id="stredocesky-live-smoke",
                http=http,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )
            health = await adapter.healthcheck(ctx)
            if health.status.value == "UNAVAILABLE":
                raise RuntimeError(
                    f"Středočeský public source unavailable: {health.detail}"
                )
            page = await adapter.discover(ctx, None)
            if not page.items:
                raise RuntimeError(
                    "Středočeský official funds guide produced zero programmes"
                )
            first = (await adapter.fetch_record(ctx, page.items[0])).record
            if first is None:
                raise RuntimeError("Středočeský first programme did not materialize")
            if first.raw_fields.get("coverage") != "LIMITED_STREDOCESKE_FONDY_GUIDE":
                raise RuntimeError("Středočeský coverage marker is missing")
            print(
                {
                    "health": health.status.value,
                    "programmeCount": page.total_hint,
                    "first": first.external_id,
                    "status": first.native_status,
                    "coverage": first.raw_fields.get("coverage"),
                    "sourcePage": first.raw_fields.get("sourcePage"),
                }
            )


if __name__ == "__main__":
    asyncio.run(main())
