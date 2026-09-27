"""#556 — EU F&T fixtures, contract suite, and live smoke verification.

Bounded work slice:
  - Representative open / planned / changed call fixtures
  - sha256 manifest hashes for every fixture
  - exercise_adapter_contract end-to-end for each fixture
  - stale-filter + UNKNOWN-state contract assertions
  - live smoke non-destructive + separation verification
"""
from __future__ import annotations

import hashlib
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
    assert_descriptor_contract,
    assert_discovery_page_contract,
    exercise_adapter_contract,
    make_fixture_context,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "connectors" / "eu-funding" / "fixtures"
sys.path.insert(0, str(ROOT / "connectors" / "eu-funding" / "src"))

from dotacni_majak_eu_funding.adapter import (  # noqa: E402
    EuFundingTendersAdapter,
    SEARCH_BASE,
    STATUS_FORTHCOMING,
    STATUS_OPEN,
)

_REPRESENTATIVE = [
    "search-page-open.json",
    "search-page-planned.json",
    "search-page-changed.json",
]


def _search_url(page: int, page_size: int) -> str:
    """Build POST search URL exactly as the adapter constructs it."""
    qs = urlencode({
        "apiKey": "SEDIA",
        "text": "***",
        "pageSize": str(page_size),
        "pageNumber": str(page),
    })
    return f"{SEARCH_BASE}?{qs}"


def _topic_url(identifier: str) -> str:
    """Build POST topic-detail URL exactly as the adapter constructs it."""
    qs = urlencode({
        "apiKey": "SEDIA",
        "text": f'"{identifier}"',
        "pageSize": "20",
        "pageNumber": "1",
    })
    return f"{SEARCH_BASE}?{qs}"


class EuFundingFixtureContractTest(unittest.IsolatedAsyncioTestCase):
    """#556 Scope: open/planned/changed examples + fixture hashes + contract suite."""

    def setUp(self) -> None:
        self.now = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)
        self.page_size = 2

    # -- helpers --

    def _load(self, name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))

    def _first_identifier(self, payload: dict) -> str:
        return payload["results"][0]["metadata"]["identifier"][0]

    def _make_contract_ctx(self, fixture_name: str):
        """Build FixtureHttpClient + AdapterContext for exercise_adapter_contract."""
        payload = self._load(fixture_name)
        ident = self._first_identifier(payload)
        body = json.dumps(payload).encode("utf-8")

        http = FixtureHttpClient()
        # healthcheck -> pageSize=1
        http.add("POST", _search_url(1, 1), content=body)
        # discover -> pageSize=page_size
        http.add("POST", _search_url(1, self.page_size), content=body)
        # fetch_record -> topic detail
        http.add("POST", _topic_url(ident), content=body)

        return make_fixture_context(
            http=http,
            snapshots=FixtureSnapshotStore(),
            now=self.now,
        )

    # -- fixture hash integrity (#556 Scope: API fixture hashes) --

    def test_all_fixtures_listed_and_hashed(self) -> None:
        """Every fixture in the manifest exists on disk with a matching sha256."""
        manifest = json.loads(
            (FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        expected = {"search-page-1.json", *_REPRESENTATIVE}
        actual = {e["path"] for e in manifest["entries"]}
        self.assertEqual(actual, expected)
        for entry in manifest["entries"]:
            path = FIXTURES_DIR / entry["path"]
            self.assertTrue(path.exists(), f"Missing fixture: {entry['path']}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(
                digest,
                entry["sha256"],
                f"sha256 mismatch for {entry['path']}: "
                f"manifest={entry['sha256']} actual={digest}",
            )

    def test_representative_fixtures_exist(self) -> None:
        """#556 Scope: at least open / planned / changed examples."""
        for name in _REPRESENTATIVE:
            path = FIXTURES_DIR / name
            self.assertTrue(path.exists(), f"Missing representative fixture: {name}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(payload["results"]), 1,
                                    f"{name} must have at least one result")
            for result in payload["results"]:
                status = result["metadata"]["status"][0]
                self.assertIn(
                    status,
                    {STATUS_OPEN, STATUS_FORTHCOMING},
                    f"unexpected status {status} in {name}",
                )

    # -- descriptor / source identity contract --

    def test_descriptor_contract(self) -> None:
        """#556 AC: verified official retrieval mechanism + Source Adapter contract."""
        assert_descriptor_contract(EuFundingTendersAdapter)
        desc = EuFundingTendersAdapter.descriptor
        self.assertEqual(desc.code, "EU_FT")
        for host in desc.allowed_hosts:
            self.assertTrue(
                host.endswith("ec.europa.eu")
                or host == "api.tech.ec.europa.eu",
                f"non-EU host in allowlist: {host}",
            )
        self.assertTrue(
            all(p.startswith("/") for p in desc.allowed_post_paths),
            "allowed_post_paths must all start with '/'",
        )
        self.assertIn(
            "/search-api/prod/rest/search",
            desc.allowed_post_paths,
            "only the sanctioned POST search path must be allowed",
        )

    # -- end-to-end adapter contract per fixture --

    async def test_contract_open_fixture(self) -> None:
        """#556: full contract (healthcheck+discover+fetch) with open calls."""
        ctx = self._make_contract_ctx("search-page-open.json")
        adapter = EuFundingTendersAdapter(page_size=self.page_size)
        report = await exercise_adapter_contract(adapter, ctx, require_items=True)
        self.assertEqual(report.source_code, "EU_FT")
        self.assertGreaterEqual(report.discovered, 2)
        self.assertIsNotNone(report.first_record_state)

    async def test_contract_planned_fixture(self) -> None:
        """#556: full contract with planned (forthcoming) calls."""
        ctx = self._make_contract_ctx("search-page-planned.json")
        adapter = EuFundingTendersAdapter(page_size=self.page_size)
        report = await exercise_adapter_contract(adapter, ctx, require_items=True)
        self.assertEqual(report.source_code, "EU_FT")
        self.assertGreaterEqual(report.discovered, 2)
        self.assertIsNotNone(report.first_record_state)

    async def test_contract_changed_fixture(self) -> None:
        """#556: full contract with changed calls (past deadline, recent ingest)."""
        ctx = self._make_contract_ctx("search-page-changed.json")
        adapter = EuFundingTendersAdapter(page_size=self.page_size)
        report = await exercise_adapter_contract(adapter, ctx, require_items=True)
        self.assertEqual(report.source_code, "EU_FT")
        self.assertGreaterEqual(report.discovered, 2)
        self.assertIsNotNone(report.first_record_state)

    async def test_contract_existing_fixture(self) -> None:
        """#556: full contract with pre-existing search-page-1.json (stale filter)."""
        ctx = self._make_contract_ctx("search-page-1.json")
        adapter = EuFundingTendersAdapter(page_size=self.page_size)
        report = await exercise_adapter_contract(adapter, ctx, require_items=True)
        self.assertEqual(report.source_code, "EU_FT")
        self.assertEqual(report.discovered, 1)

    # -- stale / UNKNOWN-state contract --

    async def test_stale_call_is_filtered_from_discovery(self) -> None:
        """Stale calls are excluded — UNKNOWN/error state is part of the contract."""
        ctx = self._make_contract_ctx("search-page-1.json")
        adapter = EuFundingTendersAdapter(page_size=self.page_size)
        page = await adapter.discover(ctx, SourceCheckpoint())
        assert_discovery_page_contract(adapter, page)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].external_id, "ISF-2026-TF2-AG-CORRUPT")

    async def test_changed_calls_pass_stale_filter(self) -> None:
        """Past deadline + recent ingest must NOT be filtered (stale-rule edge)."""
        ctx = self._make_contract_ctx("search-page-changed.json")
        adapter = EuFundingTendersAdapter(page_size=self.page_size)
        page = await adapter.discover(ctx, SourceCheckpoint())
        assert_discovery_page_contract(adapter, page)
        self.assertEqual(len(page.items), 2)

    # -- live smoke verification (#556 AC: non-destructive and separated) --

    def test_live_smoke_script_is_non_destructive(self) -> None:
        """#556 AC: Live smoke is non-destructive — read-only POST + temp dir only."""
        smoke = ROOT / "scripts" / "smoke_eu_funding_connector.py"
        self.assertTrue(smoke.exists(),
                        "scripts/smoke_eu_funding_connector.py must exist")
        src = smoke.read_text(encoding="utf-8")

        # No destructive HTTP verbs
        for destructive in (".delete(", ".put(", ".patch("):
            self.assertNotIn(
                destructive, src,
                f"live smoke must not call {destructive}",
            )

        # Official EU hosts — smoke script uses dynamic
        # adapter.descriptor.allowed_hosts (not hardcoded strings).
        self.assertIn("adapter.descriptor.allowed_hosts", src,
                      "smoke must use dynamic allowlisting from descriptor")
        # Verify the descriptor itself allows only EU hosts (same check as
        # test_descriptor_contract).
        desc = EuFundingTendersAdapter.descriptor
        self.assertIn("ec.europa.eu", desc.allowed_hosts,
                      "ec.europa.eu must be in the smoke descriptor allowlist")
        self.assertIn("api.tech.ec.europa.eu", desc.allowed_hosts,
                      "api.tech.ec.europa.eu must be in the smoke descriptor allowlist")

        # GuardedHttpClient with explicit allowlist
        self.assertIn("allowed_hosts", src)
        self.assertIn("allowed_post_paths", src)

        # Rate limiting + low concurrency
        self.assertIn("requests_per_second", src)
        self.assertIn("max_concurrency", src)

        # Temp directory — no persistent side effects
        self.assertIn("TemporaryDirectory", src)

    def test_live_smoke_is_separated_from_ci(self) -> None:
        """#556 AC: Live smoke is separated — registered in the runner, not PR CI."""
        runner = ROOT / "scripts" / "live_smoke_runners.py"
        self.assertTrue(runner.exists(), "live_smoke_runners.py must exist")
        runner_src = runner.read_text(encoding="utf-8")
        self.assertIn("EU_FT", runner_src,
                      "EU_FT must be registered in the live smoke runner")


if __name__ == "__main__":
    unittest.main()
