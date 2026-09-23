import asyncio
import json
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "applicant" / "src"))

from dotacni_majak_applicant import (
    AresResolver,
    InMemoryMunicipalityPopulationResolver,
    MunicipalityPopulation,
    ResolutionStatus,
)
from dotacni_majak_source_sdk import GuardedHttpClient


FIXTURES = ROOT / "tests" / "fixtures" / "ares"


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class AresResolverTest(unittest.IsolatedAsyncioTestCase):
    async def make_client(self, payload, status=200):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                status,
                json=payload,
                request=request,
            )
        )
        return GuardedHttpClient(
            allowed_hosts={"ares.gov.cz"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=transport,
        )

    async def test_current_shape_resolves_minimal_profile_facts(self):
        payload = json.loads(
            (FIXTURES / "current-shape.json").read_text(encoding="utf-8")
        )
        client = await self.make_client(payload)
        try:
            result = await AresResolver(client).resolve("12345678")
        finally:
            await client.aclose()

        self.assertEqual(result.status, ResolutionStatus.RESOLVED)
        facts = result.fact_map()
        self.assertEqual(facts["applicant.ico"], "12345678")
        self.assertEqual(
            facts["applicant.organisation_name"],
            "Testovací organizace",
        )
        self.assertEqual(facts["applicant.legal_form"], "706")
        self.assertEqual(
            facts["applicant.municipality.code"],
            "123456",
        )
        self.assertEqual(
            facts["applicant.cz_nace"],
            ["93120", "94990"],
        )
        self.assertNotIn("applicant.type", facts)

    async def test_alternate_shape_is_tolerated_without_guessing_type(self):
        payload = json.loads(
            (FIXTURES / "alternate-shape.json").read_text(encoding="utf-8")
        )
        client = await self.make_client(payload)
        try:
            result = await AresResolver(client).resolve("12345678")
        finally:
            await client.aclose()

        self.assertEqual(result.status, ResolutionStatus.RESOLVED)
        facts = result.fact_map()
        self.assertEqual(
            facts["applicant.organisation_name"],
            "Testovací organizace",
        )
        self.assertEqual(facts["applicant.legal_form"], "706")
        self.assertNotIn("applicant.type", facts)

    async def test_invalid_ico_never_hits_network(self):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={}, request=request)

        client = GuardedHttpClient(
            allowed_hosts={"ares.gov.cz"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(handler),
        )
        try:
            result = await AresResolver(client).resolve("123")
        finally:
            await client.aclose()

        self.assertEqual(result.status, ResolutionStatus.INVALID_INPUT)
        self.assertEqual(calls, 0)

    async def test_404_is_not_found_not_ineligible(self):
        client = await self.make_client({}, status=404)
        try:
            result = await AresResolver(client).resolve("12345678")
        finally:
            await client.aclose()
        self.assertEqual(result.status, ResolutionStatus.NOT_FOUND)

    async def test_mismatched_ico_is_unavailable_contract_error(self):
        client = await self.make_client({
            "ico": "87654321",
            "obchodniJmeno": "Wrong",
        })
        try:
            result = await AresResolver(client).resolve("12345678")
        finally:
            await client.aclose()
        self.assertEqual(result.status, ResolutionStatus.UNAVAILABLE)


class PopulationResolverTest(unittest.IsolatedAsyncioTestCase):
    async def test_population_record_keeps_as_of_and_source(self):
        record = MunicipalityPopulation(
            municipality_code="123456",
            population=3200,
            as_of=date(2025, 12, 31),
            source_reference="CZSO:OBY02E",
            observed_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        )
        resolver = InMemoryMunicipalityPopulationResolver({
            "123456": record
        })
        resolved = await resolver.resolve("123456")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.population, 3200)
        self.assertEqual(resolved.source_reference, "CZSO:OBY02E")


if __name__ == "__main__":
    unittest.main()
