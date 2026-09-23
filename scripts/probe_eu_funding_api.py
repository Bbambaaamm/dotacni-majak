from __future__ import annotations

import asyncio
import json

from dotacni_majak_source_sdk import GuardedHttpClient


URL = (
    "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    "?apiKey=SEDIA&text=***&pageSize=2&pageNumber=1"
)


async def main() -> None:
    query = {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "8"]}},
                {"terms": {"status": ["31094501", "31094502"]}},
                {"term": {"programmePeriod": "2021 - 2027"}},
            ]
        }
    }

    async with GuardedHttpClient(
        allowed_hosts={"api.tech.ec.europa.eu"},
        allowed_post_paths={"/search-api/prod/rest/search"},
        requests_per_second=0.5,
        max_concurrency=1,
        max_response_bytes=5 * 1024 * 1024,
        max_request_body_bytes=64 * 1024,
    ) as client:
        response = await client.post_multipart(
            URL,
            json_parts={
                "query": query,
                "languages": ["en"],
                "sort": {"field": "sortStatus", "order": "ASC"},
            },
            text_parts={"displayLanguage": "en"},
        )

    print(f"HTTP_STATUS={response.status_code}")
    payload = json.loads(response.text)
    print("TOP_LEVEL_KEYS=" + json.dumps(sorted(payload.keys())))

    results = payload.get("results") or []
    print(f"RESULT_COUNT={len(results)}")
    print(f"TOTAL_RESULTS={payload.get('totalResults')}")

    if not results:
        return

    first = results[0]
    print("RESULT_KEYS=" + json.dumps(sorted(first.keys())))
    metadata = first.get("metadata") or {}
    if isinstance(metadata, dict):
        print("METADATA_KEYS=" + json.dumps(sorted(metadata.keys())))

    interesting = {}
    for key in (
        "reference",
        "url",
        "summary",
        "identifier",
        "title",
        "status",
        "startDate",
        "deadlineDate",
        "frameworkProgramme",
        "callTitle",
        "type",
    ):
        if key in first:
            interesting[f"top.{key}"] = first[key]
        if isinstance(metadata, dict) and key in metadata:
            interesting[f"metadata.{key}"] = metadata[key]

    print(
        "INTERESTING="
        + json.dumps(interesting, ensure_ascii=False, default=str)[:10000]
    )


if __name__ == "__main__":
    asyncio.run(main())
