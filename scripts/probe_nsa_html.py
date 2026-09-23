from __future__ import annotations

import asyncio
from bs4 import BeautifulSoup

from dotacni_majak_source_sdk import GuardedHttpClient


LISTING = "https://nsa.gov.cz/dotace-investicni/"
DETAIL = "https://nsa.gov.cz/dotace/vyzva-16-2026-regiony-26-investice-pod-10-mil-kc/"


async def fetch(client: GuardedHttpClient, url: str) -> str:
    response = await client.get(url)
    print(f"URL={url}")
    print(f"STATUS={response.status_code}")
    print(f"CONTENT_TYPE={response.headers.get('content-type')}")
    if response.status_code != 200:
        raise SystemExit(f"Unexpected HTTP {response.status_code}")
    return response.text


async def main() -> None:
    async with GuardedHttpClient(
        allowed_hosts={"nsa.gov.cz"},
        requests_per_second=0.5,
        max_concurrency=1,
        max_response_bytes=5 * 1024 * 1024,
    ) as client:
        listing_html = await fetch(client, LISTING)
        detail_html = await fetch(client, DETAIL)

    listing = BeautifulSoup(listing_html, "html.parser")
    print("LISTING_TITLE=" + (listing.title.get_text(" ", strip=True) if listing.title else ""))
    for heading in listing.find_all(["h1", "h2", "h3", "h4"]):
        text = heading.get_text(" ", strip=True)
        if text:
            print(f"HEADING:{heading.name}:{text[:180]}")

    call_links = []
    for a in listing.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if "/dotace/vyzva-" in href:
            call_links.append((text, href, a.parent.name if a.parent else ""))
    print(f"CALL_LINK_COUNT={len(call_links)}")
    for text, href, parent in call_links[:40]:
        print(f"CALL_LINK:{parent}:{text[:160]}::{href}")

    detail = BeautifulSoup(detail_html, "html.parser")
    h1 = detail.find("h1")
    print("DETAIL_H1=" + (h1.get_text(" ", strip=True) if h1 else ""))
    for heading in detail.find_all(["h2", "h3", "h4"]):
        text = heading.get_text(" ", strip=True)
        if text:
            print(f"DETAIL_HEADING:{heading.name}:{text[:200]}")

    body_text = detail.get_text("\n", strip=True)
    for marker in (
        "DATUM VYHLÁŠENÍ VÝZVY",
        "ZAHÁJENÍ PŘÍJMU ŽÁDOSTÍ",
        "UKONČENÍ PŘÍJMU ŽÁDOSTÍ",
        "ALOKACE",
        "TYP VÝZVY",
        "Příjem žádostí byl ukončen",
    ):
        pos = body_text.find(marker)
        if pos >= 0:
            print("DETAIL_CONTEXT=" + body_text[pos:pos+500].replace("\n", " | "))

    docs = []
    for a in detail.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if (
            "/wp-content/uploads/" in href
            or href.lower().endswith((".pdf", ".docx", ".xlsx", ".doc"))
        ):
            docs.append((text, href))
    print(f"DOC_LINK_COUNT={len(docs)}")
    for text, href in docs[:50]:
        print(f"DOC:{text[:180]}::{href}")


if __name__ == "__main__":
    asyncio.run(main())
