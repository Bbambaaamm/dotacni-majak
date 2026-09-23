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

            # The official Středočeský website is known to time out from some
            # GitHub-hosted runners. That is a Source Health condition, not a
            # parser failure and must not encourage bypassing the source.
            if health.status.value == "UNAVAILABLE":
                print(
                    {
                        "health": health.status.value,
                        "coverage": "LIMITED_STREDOCESKE_FONDY_GUIDE",
                        "note": (
                            "Official source is unreachable from this runner. "
                            "Connector stays LIMITED/DEGRADED; no bypass attempted."
                        ),
                        "detail": health.detail,
                    }
                )
                return

            page = await adapter.discover(ctx, None)
            if not page.items:
                raise RuntimeError(
                    "Reachable Středočeský official funds guide produced zero programmes"
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
