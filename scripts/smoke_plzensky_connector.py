from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_plzensky import PlzenskyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


async def main() -> None:
    adapter = PlzenskyAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        async with GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            requests_per_second=adapter.descriptor.requests_per_second,
            max_concurrency=adapter.descriptor.max_concurrency,
            max_response_bytes=20 * 1024 * 1024,
        ) as client:
            ctx = AdapterContext(
                run_id="plzensky-live-smoke",
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
                import re
                response = await client.get("https://dotace.plzensky-kraj.cz/verejnost")
                html = response.text
                signals = []
                for pattern in (
                    r'https?://[^"\'<> ]+',
                    r'[^"\']*dotacnititul[^"\']*',
                    r'<form[^>]+>',
                    r'<script[^>]+src=["\'][^"\']+',
                ):
                    for match in re.findall(pattern, html, re.I):
                        value = " ".join(match.split())
                        if value not in signals:
                            signals.append(value)
                        if len(signals) >= 40:
                            break
                    if len(signals) >= 40:
                        break
                print("diagnostic-signals")
                for signal in signals:
                    print(signal[:500])

                for needle in (
                    "DotacniTitulyOtevrene",
                    "DotacniTitulyPripravovane",
                    "/verejnost/dotacnitituly",
                    "jqGrid",
                    "datatype",
                    "postData",
                ):
                    start = 0
                    printed = 0
                    while printed < 3:
                        pos = html.find(needle, start)
                        if pos < 0:
                            break
                        left = max(0, pos - 1200)
                        right = min(len(html), pos + 2200)
                        context = " ".join(html[left:right].split())
                        print("html-context", needle, context[:3400])
                        start = pos + len(needle)
                        printed += 1

                raise SystemExit("Plzeň live smoke discovered zero open/planned calls")
            first = page.items[0]
            result = await adapter.fetch_record(ctx, first)
            record = result.record
            if record is None or not record.snapshot_ids:
                raise SystemExit("Plzeň detail did not produce RAW-backed record")
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
