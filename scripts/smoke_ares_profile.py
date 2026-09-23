import asyncio

from dotacni_majak_applicant import AresResolver, ResolutionStatus
from dotacni_majak_source_sdk import GuardedHttpClient


async def main() -> None:
    async with GuardedHttpClient(
        allowed_hosts={"ares.gov.cz"},
        requests_per_second=1.0,
        max_concurrency=1,
        timeout_seconds=20,
    ) as http:
        result = await AresResolver(http).resolve("00006947")
        if result.status != ResolutionStatus.RESOLVED:
            raise SystemExit(
                f"ARES profile smoke failed: {result.status} {result.warnings}"
            )
        facts = result.fact_map()
        for required in (
            "applicant.ico",
            "applicant.organisation_name",
            "applicant.legal_form",
        ):
            if not facts.get(required):
                raise SystemExit(f"ARES missing expected fact: {required}")
        print(
            "ARES profile smoke OK:",
            facts["applicant.ico"],
            facts["applicant.organisation_name"],
        )


if __name__ == "__main__":
    asyncio.run(main())
