from __future__ import annotations

import asyncio

from dotacni_majak_source_sdk import GuardedHttpClient


URLS = {
    "dotace": (
        "https://red.financnisprava.cz/opendata/dataset/"
        "96e09eae-5b16-47d6-9606-416b0d9eab19/resource/"
        "75e035a1-36b0-4558-be88-02e79bf9b187/download/dotace.csv.gz"
    ),
    "prijemce": (
        "https://red.financnisprava.cz/opendata/dataset/"
        "5d65bb4d-5694-4166-a69b-579d6ab2f5cb/resource/"
        "3f734767-2c06-47fe-87d1-c3bff1d40cd3/download/prijemce.csv.gz"
    ),
    "rozhodnuti": (
        "https://red.financnisprava.cz/opendata/dataset/"
        "eb331c5f-3f4f-4be7-9543-96834d12b924/resource/"
        "f4d9e003-a3f2-48a3-9cee-b7151d5d1e6d/download/rozhodnuti.csv.gz"
    ),
}


async def main() -> None:
    async with GuardedHttpClient(
        allowed_hosts={"red.financnisprava.cz"},
        requests_per_second=0.5,
        max_concurrency=1,
        retries=1,
    ) as client:
        failures: list[tuple[str, int]] = []
        for name, url in URLS.items():
            response = await client.request("HEAD", url)
            print(name, response.status_code, response.headers.get("content-type"))
            if response.status_code >= 400:
                failures.append((name, response.status_code))
        if failures:
            raise SystemExit(f"ReD smoke failed: {failures!r}")


if __name__ == "__main__":
    asyncio.run(main())
