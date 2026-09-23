import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "stredocesky" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient
from dotacni_majak_stredocesky.adapter import (
    ROOT_URL,
    StredoceskyAdapter,
    _find_guide_url,
    entries_from_page_texts,
)


ROOT_HTML = (
    ROOT / "connectors" / "stredocesky" / "fixtures" / "root.html"
).read_text(encoding="utf-8")
RAW_PAGES = (
    ROOT / "connectors" / "stredocesky" / "fixtures" / "guide-pages.txt"
).read_text(encoding="utf-8")
GUIDE_PAGES = [
    part.strip()
    for part in __import__("re").split(r"===PAGE \d+===", RAW_PAGES)
    if part.strip()
]
GUIDE_URL = "https://stredoceskykraj.cz/documents/d/dotace/sf_prirucka_2026_verze_iv"


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class StredoceskyAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(ROOT_URL):
            return httpx.Response(
                200,
                text=ROOT_HTML,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if request.url.path.endswith("/sf_prirucka_2026_verze_iv"):
            return httpx.Response(
                200,
                content=b"%PDF-fixture",
                headers={"content-type": "application/pdf", "etag": '"guide-v4"'},
                request=request,
            )
        return httpx.Response(404, request=request)

    def context(self, tmp):
        adapter = StredoceskyAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        ctx = AdapterContext(
            run_id="stc-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )
        return adapter, client, ctx

    def test_finds_current_official_guide_link(self):
        self.assertEqual(_find_guide_url(ROOT_HTML), GUIDE_URL)

    def test_page_text_parser_extracts_limited_programmes(self):
        items = entries_from_page_texts(
            GUIDE_PAGES,
            guide_url=GUIDE_URL,
            guide_snapshot_id="raw:STC:guide",
            root_snapshot_id="raw:STC:root",
            guide_sha256="a" * 64,
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(items), 2)
        by_title = {item.title_hint: item for item in items}
        prevention = next(
            item for title, item in by_title.items()
            if "prevence" in (title or "").casefold()
        )
        village = next(
            item for title, item in by_title.items()
            if "obnovy venkova" in (title or "").casefold()
        )
        self.assertEqual(prevention.native_status_hint, "OPEN")
        self.assertEqual(village.native_status_hint, "OPEN")
        self.assertEqual(prevention.metadata["cofinancing_text"], "min. 5 %.")
        self.assertEqual(village.metadata["region_code"], "CZ020")
        self.assertEqual(
            village.metadata["coverage"],
            "LIMITED_STREDOCESKE_FONDY_GUIDE",
        )

    async def test_discovery_is_raw_backed_and_fetch_record_uses_page_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = self.context(tmp)
            try:
                with patch(
                    "dotacni_majak_stredocesky.adapter._extract_pdf_pages",
                    return_value=GUIDE_PAGES,
                ):
                    page = await adapter.discover(ctx, None)
                record = (await adapter.fetch_record(ctx, page.items[0])).record
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 2)
        self.assertIsNotNone(record)
        self.assertEqual(record.raw_fields["regionCode"], "CZ020")
        self.assertTrue(record.raw_fields["sourceDocumentUrl"].startswith("https://"))
        self.assertIsInstance(record.raw_fields["sourcePage"], int)
        self.assertEqual(
            record.raw_fields["coverage"],
            "LIMITED_STREDOCESKE_FONDY_GUIDE",
        )
        self.assertEqual(len(record.snapshot_ids), 2)
        self.assertTrue(all(value and not value.endswith("None") for value in record.snapshot_ids))

    async def test_known_record_hash_is_not_modified(self):
        items = entries_from_page_texts(
            GUIDE_PAGES,
            guide_url=GUIDE_URL,
            guide_snapshot_id="raw:STC:guide",
            root_snapshot_id="raw:STC:root",
            guide_sha256="a" * 64,
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = self.context(tmp)
            try:
                from dotacni_majak_source_sdk import FetchValidators
                result = await adapter.fetch_record(
                    ctx,
                    items[0],
                    FetchValidators(
                        known_sha256=items[0].metadata["record_hash"]
                    ),
                )
            finally:
                await client.aclose()
        self.assertEqual(result.state.value, "NOT_MODIFIED")

    async def test_health_uses_public_dotace_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
            finally:
                await client.aclose()
        self.assertEqual(health.status.value, "HEALTHY")


if __name__ == "__main__":
    unittest.main()
