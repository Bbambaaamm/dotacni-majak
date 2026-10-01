from __future__ import annotations

import asyncio
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from dotacni_majak_source_sdk import SourceCheckpoint
from dotacni_majak_source_sdk.testing import (
    FixtureHttpClient,
    FixtureSnapshotStore,
    assert_discovery_page_contract,
    make_fixture_context,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "eu-funding" / "src"))

from dotacni_majak_eu_funding.adapter import EuFundingTendersAdapter

EU_FT_SEARCH_BASE = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"


def eu_ft_search_url(page: int, page_size: int = 2) -> str:
    qs = urlencode({
        "apiKey": "SEDIA",
        "text": "***",
        "pageSize": str(page_size),
        "pageNumber": str(page),
    })
    return f"{EU_FT_SEARCH_BASE}?{qs}"


def make_eu_ft_page(
    page_number: int,
    page_size: int,
    total_results: int,
    identifiers: list[str],
    statuses: list[str],
) -> dict:
    results: list[dict] = []
    for i, ident in enumerate(identifiers):
        results.append({
            "reference": f"REF-{ident}",
            "url": f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ident}",
            "summary": f"Call for proposals {ident}",
            "metadata": {
                "identifier": [ident],
                "title": [f"Call for proposals {ident}"],
                "status": [statuses[i]],
                "type": ["1"],
                "frameworkProgramme": ["43252368"],
            },
        })
    return {
        "apiVersion": "real-contract-fixture-2026-09-23",
        "pageNumber": page_number,
        "pageSize": page_size,
        "totalResults": total_results,
        "results": results,
    }


class EuFundingCheckpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)

    def _adapter(self, page_size: int = 2) -> EuFundingTendersAdapter:
        return EuFundingTendersAdapter(page_size=page_size)

    async def test_discovery_checkpoint_resume(self) -> None:
        """Checkpoint cursor resumes discovery at the correct page."""
        page_size = 2
        page1 = make_eu_ft_page(1, page_size, 4,
                                ["ISF-2026-TF2-AG-CORRUPT", "HEALTH-2026-TF1"],
                                ["31094502", "31094502"])
        page2 = make_eu_ft_page(2, page_size, 4,
                                ["AGRI-2026-TF3", "DIGI-2026-TF4"],
                                ["31094502", "31094502"])

        http = FixtureHttpClient()
        http.add("POST", eu_ft_search_url(1, page_size),
                 content=json.dumps(page1).encode("utf-8"))
        http.add("POST", eu_ft_search_url(2, page_size),
                 content=json.dumps(page2).encode("utf-8"))

        ctx = make_fixture_context(
            http=http,
            snapshots=FixtureSnapshotStore(),
            now=self.now,
        )
        adapter = self._adapter(page_size)

        first = await adapter.discover(ctx, None)
        assert_discovery_page_contract(adapter, first)
        self.assertEqual(first.next_checkpoint.cursor, "2")
        self.assertFalse(first.is_complete)
        self.assertEqual(first.total_hint, 4)
        self.assertEqual(len(first.items), 2)

        resumed = await adapter.discover(ctx, SourceCheckpoint(cursor="2"))
        assert_discovery_page_contract(adapter, resumed)
        self.assertTrue(resumed.is_complete)
        self.assertIsNone(resumed.next_checkpoint)
        self.assertEqual(resumed.total_hint, 4)
        self.assertEqual(len(resumed.items), 2)
        self.assertEqual(
            {item.external_id for item in resumed.items},
            {"AGRI-2026-TF3", "DIGI-2026-TF4"},
        )

    async def test_discovery_completes_when_total_exhausted(self) -> None:
        """Final page reports is_complete=True and next_checkpoint=None."""
        page_size = 2
        page1 = make_eu_ft_page(1, page_size, 2,
                                ["ISF-2026-TF2-AG-CORRUPT", "HEALTH-2026-TF1"],
                                ["31094502", "31094502"])

        http = FixtureHttpClient()
        http.add("POST", eu_ft_search_url(1, page_size),
                 content=json.dumps(page1).encode("utf-8"))

        ctx = make_fixture_context(
            http=http,
            snapshots=FixtureSnapshotStore(),
            now=self.now,
        )
        adapter = self._adapter(page_size)

        result = await adapter.discover(ctx, None)
        assert_discovery_page_contract(adapter, result)
        self.assertTrue(result.is_complete)
        self.assertIsNone(result.next_checkpoint)
        self.assertEqual(result.total_hint, 2)
        self.assertEqual(len(result.items), 2)

    async def test_discovery_rejects_non_integer_checkpoint_cursor(self) -> None:
        """Non-integer checkpoint cursor raises ValueError (safe failure)."""
        http = FixtureHttpClient()
        ctx = make_fixture_context(
            http=http,
            snapshots=FixtureSnapshotStore(),
            now=self.now,
        )
        adapter = self._adapter()

        with self.assertRaises(ValueError):
            await adapter.discover(ctx, SourceCheckpoint(cursor="not-a-number"))

    async def test_discovery_page_contract_enforced(self) -> None:
        """assert_discovery_page_contract validates adapter output and
        catches duplicate external_id values (safety net for the contract)."""
        page_size = 2
        page1 = make_eu_ft_page(1, page_size, 2,
                                ["ISF-2026-TF2-AG-CORRUPT", "ISF-2026-TF2-AG-CORRUPT"],
                                ["31094502", "31094502"])

        http = FixtureHttpClient()
        http.add("POST", eu_ft_search_url(1, page_size),
                 content=json.dumps(page1).encode("utf-8"))

        ctx = make_fixture_context(
            http=http,
            snapshots=FixtureSnapshotStore(),
            now=self.now,
        )
        adapter = self._adapter(page_size)

        page = await adapter.discover(ctx, None)
        with self.assertRaises(AssertionError):
            assert_discovery_page_contract(adapter, page)


if __name__ == "__main__":
    unittest.main()
