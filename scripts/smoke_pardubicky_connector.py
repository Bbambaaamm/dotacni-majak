from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_pardubicky import PardubickyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


def _allow_source_unavailable() -> bool:
    return os.getenv("ALLOW_SOURCE_UNAVAILABLE", "").strip().lower() in {
        "1", "true", "yes"
    }


async def main() -> None:
    adapter = PardubickyAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="pardubicky-live-smoke",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )
            health = await adapter.healthcheck(ctx)
            print("health", health.status.value, health.detail)

            if health.status.value == "UNAVAILABLE":
                # Upstream transport/TLS outage is a Source Health signal, not
                # a reason to weaken TLS verification. PR runs may tolerate it
                # because fixture CI validates connector behaviour. Scheduled
                # and manually dispatched runs remain strict.
                if _allow_source_unavailable():
                    print(
                        "SOURCE_UNAVAILABLE_ALLOWED_ON_PR",
                        health.detail or "no detail",
                    )
                    return
                raise SystemExit(
                    f"Pardubický source is unavailable: {health.detail}"
                )

            if health.status.value != "HEALTHY":
                raise SystemExit(
                    f"Pardubický source is not healthy: {health.detail}"
                )

            page = await adapter.discover(ctx, None)
            print("discovered", page.total_hint)
            if not page.items:
                raise SystemExit(
                    "Pardubický live smoke discovered zero programmes"
                )

            sample = page.items[0]
            record = (await adapter.fetch_record(ctx, sample)).record
            if record is None or not record.snapshot_ids:
                raise SystemExit(
                    "Pardubický detail did not produce RAW-backed record"
                )
            if record.raw_fields.get("regionCode") != "CZ053":
                raise SystemExit("Pardubický detail has wrong region code")

            print(
                "sample",
                record.external_id,
                record.native_status,
                record.native_title,
                record.raw_fields.get("submissionOpenAt"),
                record.raw_fields.get("submissionCloseAt"),
                record.raw_fields.get("grantAmountMinMinor"),
                record.raw_fields.get("grantAmountMaxMinor"),
                len(record.artifacts),
            )


if __name__ == "__main__":
    asyncio.run(main())
