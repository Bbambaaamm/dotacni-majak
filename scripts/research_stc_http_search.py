#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from html.parser import HTMLParser


SEARCH_URL = (
    "https://idzsck.stredoceskykraj.cz/web/urad/vyhledavani"
    "?q=Program%202026"
)
ALLOWED_HOSTS = {
    "idzsck.stredoceskykraj.cz",
    "stredoceskykraj.cz",
    "www.stredoceskykraj.cz",
}
USER_AGENT = (
    "DotacniMajak-SourceResearch/0.6 "
    "(+https://github.com/Bbambaaamm/dotacni-majak)"
)


class PublicLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append(
            {
                "href": self._href,
                "text": " ".join("".join(self._text).split())[:350],
            }
        )
        self._href = None
        self._text = []


def safe_public_link(raw: str, base: str) -> dict[str, object] | None:
    url = urllib.parse.urljoin(base, raw)
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_HOSTS:
        return None
    return {
        "href": url,
        "origin": f"https://{host}",
        "pathname": parsed.path,
        "queryKeys": sorted(set(urllib.parse.parse_qs(parsed.query).keys())),
    }


def main() -> None:
    request = urllib.request.Request(
        SEARCH_URL,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    context = ssl.create_default_context()
    error = None
    status = None
    final_url = None
    content_type = None
    public_links: list[dict[str, object]] = []
    body_preview = None

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
            context=context,
        ) as response:
            status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("content-type")
            body = response.read(5 * 1024 * 1024)
        text = body.decode("utf-8", errors="replace")
        parser = PublicLinkParser()
        parser.feed(text)

        seen: set[str] = set()
        for item in parser.links:
            safe = safe_public_link(item["href"], final_url or SEARCH_URL)
            if not safe or safe["href"] in seen:
                continue
            haystack = (
                item["text"] + " " + str(safe["pathname"])
            ).casefold()
            if not (
                "/web/dotace/" in str(safe["pathname"]).casefold()
                or "/documents/" in str(safe["pathname"]).casefold()
                or "program" in haystack
                or "dotac" in haystack
                or "fond" in haystack
            ):
                continue
            seen.add(str(safe["href"]))
            public_links.append({"text": item["text"], **safe})
            if len(public_links) >= 200:
                break

        visible = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
        visible = re.sub(r"<style\b[^>]*>.*?</style>", " ", visible, flags=re.I | re.S)
        visible = re.sub(r"<[^>]+>", " ", visible)
        visible = " ".join(visible.split())
        body_preview = visible[:7000]
    except Exception as exc:  # research probe intentionally reports, not hides
        error = f"{type(exc).__name__}: {exc}"

    print(
        json.dumps(
            {
                "requestedUrl": SEARCH_URL,
                "status": status,
                "finalUrl": final_url,
                "contentType": content_type,
                "publicLinks": public_links,
                "bodyPreview": body_preview,
                "note": (
                    "Simple public HTTPS GET only. No login, cookies, auth headers, "
                    "CAPTCHA bypass, protected grant portal access or request body."
                ),
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
