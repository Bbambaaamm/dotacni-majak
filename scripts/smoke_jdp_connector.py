from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_jdp import JdpAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient, HealthStatus


async def smoke_attempt(attempt: int) -> None:
    adapter = JdpAdapter(page_size=8)
    async with GuardedHttpClient(
        allowed_hosts=set(adapter.descriptor.allowed_hosts),
        allowed_post_paths=set(adapter.descriptor.allowed_post_paths),
        requests_per_second=0.5,
        max_concurrency=1,
        max_response_bytes=10 * 1024 * 1024,
        timeout_seconds=35,
        retries=4,
    ) as client:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id=f"jdp-live-smoke-{attempt}",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime.now(timezone.utc),
            )

            health = await adapter.healthcheck(ctx)
            print(
                f"attempt={attempt} health={health.status.value} "
                f"detail={health.detail!r}"
            )
            if health.status is not HealthStatus.HEALTHY:
                raise RuntimeError(
                    f"JDP source health is {health.status.value}: {health.detail}"
                )

            page = await adapter.discover(ctx, None)
            print(
                f"attempt={attempt} discovered={len(page.items)} "
                f"total={page.total_hint}"
            )
            if not page.items:
                raise RuntimeError(
                    "JDP public dashboard discovered zero open calls"
                )

            record = (await adapter.fetch_record(ctx, page.items[0])).record
            if record is None or not record.snapshot_ids:
                raise RuntimeError("JDP record is not RAW-backed")

            print(
                "sample",
                record.external_id,
                record.native_status,
                record.native_title,
                record.raw_fields.get("submissionCloseAtSource"),
                record.raw_fields.get("grantAmountMaxSource"),
            )


async def main() -> None:
    last_error: Exception | None = None

    # The JDP public portal has already been verified from real unauthenticated
    # browser traffic. A cloud runner can still hit transient TLS/network
    # failures, so the live smoke retries the *whole* read-only contract a few
    # times before classifying the source as unavailable.
    for attempt in range(1, 4):
        try:
            await smoke_attempt(attempt)
            return
        except Exception as exc:
            last_error = exc
            print(
                f"attempt={attempt} failed with "
                f"{type(exc).__name__}: {exc}"
            )
            if attempt < 3:
                await asyncio.sleep(5 * attempt)

    raise SystemExit(
        "JDP live smoke failed after 3 complete attempts: "
        f"{type(last_error).__name__}: {last_error}"
    )


if __name__ == "__main__":
    asyncio.run(main())
