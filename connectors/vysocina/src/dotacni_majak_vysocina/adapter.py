from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from dotacni_majak_source_sdk import (
    AdapterContext,
    ArtifactFetchResult,
    AuthorityLevel,
    DiscoveryItem,
    DiscoveryPage,
    FetchState,
    FetchValidators,
    HealthReport,
    HealthStatus,
    NativeRecord,
    RecordFetchResult,
    RemoteArtifactRef,
    RetrievalMode,
    SourceAdapter,
    SourceCheckpoint,
    SourceDescriptor,
)


INDEX_URL = (
    "https://www.kr-vysocina.cz/vismo/rejstrik.asp"
    "?id_org=450008&p1=122604&p3=.&rh=397"
)
_ALLOWED_HOSTS = {"www.kr-vysocina.cz", "kr-vysocina.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_DETAIL_RE = re.compile(r"/d-(?P<id>\d+)(?:/|$)", re.I)
_DATE_RE = re.compile(
    r"(?P<d>\d{1,2})\.\s*(?P<m>\d{1,2})\.\s*(?P<y>20\d{2})?"
)


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _page_url(page: int) -> str:
    if page <= 1:
        return INDEX_URL
    parts = urlsplit(INDEX_URL)
    query = parse_qs(parts.query, keep_blank_values=True)
    query["pocet"] = ["24"]
    query["stranka"] = [str(page)]
    encoded = urlencode(query, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, encoded, ""))


def _pagination_pages(soup: BeautifulSoup) -> list[int]:
    pages = {1}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(INDEX_URL, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        if not parsed.path.casefold().endswith("/vismo/rejstrik.asp"):
            continue
        query = parse_qs(parsed.query)
        raw = query.get("stranka", [None])[0]
        if raw and raw.isdigit():
            pages.add(int(raw))
    return sorted(page for page in pages if 1 <= page <= 20)


def _candidate(card_text: str, year: int) -> bool:
    folded = _normalize(card_text)
    if str(year) not in folded:
        return False

    positive = (
        "vyhlasil" in folded
        or "vyhlasili" in folded
        or "vyhlaseni programu" in folded
        or "podavat zadosti" in folded
        or "zasílat zadosti" in folded
        or "zasilat zadosti" in folded
        or "termin sberu zadosti" in folded
        or "mohou od" in folded and "zadost" in folded
    )
    if not positive:
        return False

    # Aggregate policy/roundup articles are useful context, but one article
    # must not be normalized as one grant when it actually describes many.
    if re.search(r"vyhlasil[ia]?\s+dalsich\s+\w*\s*program", folded):
        return False
    if "dotacni politiku" in folded and "programy" in folded:
        return False
    return True


def _article_links(soup: BeautifulSoup, page_url: str, year: int) -> list[tuple[str, str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        match = _DETAIL_RE.search(parsed.path)
        if not match:
            continue
        card = anchor.find_parent(["li", "article", "div"])
        card_text = _clean(card.get_text(" ", strip=True)) if card else ""
        label = _clean(anchor.get_text(" ", strip=True))
        combined = f"{label} {card_text}"
        if not _candidate(combined, year):
            continue
        result[url] = (label or card_text[:500], card_text[:5000])
    return [(url, title, card) for url, (title, card) in sorted(result.items())]


def _external_id(url: str) -> str:
    match = _DETAIL_RE.search(urlsplit(url).path)
    if not match:
        raise ValueError(f"not a Vysočina detail URL: {url}")
    return f"VYS-{match.group('id')}"


def _application_window(body: str) -> tuple[datetime | None, datetime | None, str | None]:
    folded = _normalize(body)
    for marker in ("zadosti", "zadost", "termin sberu"):
        start = 0
        while True:
            pos = folded.find(marker, start)
            if pos < 0:
                break
            left = max(0, pos - 220)
            right = min(len(body), pos + 420)
            fragment = body[left:right]
            matches = list(_DATE_RE.finditer(fragment))
            if len(matches) >= 2:
                first, second = matches[0], matches[1]
                y2 = second.group("y")
                y1 = first.group("y") or y2
                if y1 and y2:
                    open_local = datetime(
                        int(y1), int(first.group("m")), int(first.group("d")),
                        0, 0, 0, tzinfo=_LOCAL_TZ,
                    )
                    close_local = datetime(
                        int(y2), int(second.group("m")), int(second.group("d")),
                        23, 59, 59, tzinfo=_LOCAL_TZ,
                    )
                    # Preserve an explicit closing time if present nearby.
                    after_second = fragment[second.end():second.end() + 30]
                    tm = re.search(r"(\d{1,2})[:.]([0-5]\d)", after_second)
                    if tm:
                        close_local = close_local.replace(
                            hour=int(tm.group(1)),
                            minute=int(tm.group(2)),
                            second=0,
                        )
                    return (
                        open_local.astimezone(timezone.utc),
                        close_local.astimezone(timezone.utc),
                        _clean(fragment),
                    )
            start = pos + len(marker)
    return None, None, None


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    if not opens or not closes:
        return "ANNOUNCED"
    current = now.astimezone(timezone.utc)
    if current < opens:
        return "PLANNED"
    if current > closes:
        return "CLOSED"
    return "OPEN"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS or url in seen:
            continue
        path_query = (parsed.path + "?" + parsed.query).casefold()
        if not (
            "/assets/file.ashx" in path_query
            or path_query.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx"))
        ):
            continue
        seen.add(url)
        label = _clean(anchor.get_text(" ", strip=True)) or url
        folded = _normalize(label)
        role = (
            "CALL_DOCUMENT"
            if "program" in folded or "vyzva" in folded or "pravid" in folded
            else "APPLICATION_FORM"
            if "zadost" in folded or "formular" in folded
            else "ANNEX"
        )
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=label[:500],
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


class VysocinaAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="VYS",
        name="Kraj Vysočina — veřejná oznámení Fondu Vysočiny",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.kr-vysocina.cz/",
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF, RetrievalMode.DOCX],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=360,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(INDEX_URL)
            folded = _normalize(response.text)
            healthy = (
                response.status_code == 200
                and "fond vysociny" in folded
                and "heslo rejstriku" in folded
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Vysočina public index: HTTP {response.status_code}"
        except Exception as exc:
            status = HealthStatus.UNAVAILABLE
            detail = f"{type(exc).__name__}: {exc}"
        elapsed = datetime.now(timezone.utc) - started
        return HealthReport(
            status=status,
            checked_at=ctx.now,
            latency_ms=max(0, int(elapsed.total_seconds() * 1000)),
            detail=detail,
        )

    async def discover(
        self,
        ctx: AdapterContext,
        checkpoint: SourceCheckpoint | None,
    ) -> DiscoveryPage:
        del checkpoint
        target_year = ctx.now.astimezone(_LOCAL_TZ).year
        first = await ctx.http.get(INDEX_URL)
        if first.status_code >= 400:
            raise RuntimeError(f"Vysočina index returned HTTP {first.status_code}")

        first_snapshot = self._snapshot(
            ctx, source_url=INDEX_URL, content=first.content,
            mime_type=first.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=first.headers,
        )
        first_soup = BeautifulSoup(first.text, "html.parser")
        pages = _pagination_pages(first_soup)

        items: dict[str, DiscoveryItem] = {}

        async def consume(url: str, response: Any, snapshot_id: str) -> None:
            soup = BeautifulSoup(response.text, "html.parser")
            for detail_url, title, card in _article_links(soup, url, target_year):
                ext = _external_id(detail_url)
                items[ext] = DiscoveryItem(
                    external_id=ext,
                    detail_url=detail_url,
                    title_hint=title,
                    native_status_hint="ANNOUNCEMENT",
                    metadata={
                        "discovery_snapshot_id": snapshot_id,
                        "discovery_card_text": card,
                        "discovery_method": "official-fond-vysociny-news-index",
                        "coverage": "LIMITED_OFFICIAL_ANNOUNCEMENTS",
                        "target_year": target_year,
                    },
                )

        await consume(INDEX_URL, first, first_snapshot)
        for page in pages:
            if page == 1:
                continue
            url = _page_url(page)
            response = await ctx.http.get(url)
            if response.status_code >= 400:
                continue
            snapshot_id = self._snapshot(
                ctx, source_url=url, content=response.content,
                mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
                headers=response.headers,
            )
            await consume(url, response, snapshot_id)

        values = sorted(items.values(), key=lambda x: x.external_id)
        return DiscoveryPage(
            items=values,
            next_checkpoint=None,
            is_complete=True,
            total_hint=len(values),
        )

    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        headers: dict[str, str] = {}
        if validators:
            if validators.etag:
                headers["if-none-match"] = validators.etag
            if validators.last_modified:
                headers["if-modified-since"] = validators.last_modified

        response = await ctx.http.get(str(item.detail_url), headers=headers)
        if response.status_code == 304:
            return RecordFetchResult(state=FetchState.NOT_MODIFIED, http_status=304)
        if response.status_code == 404:
            return RecordFetchResult(state=FetchState.GONE, http_status=404)
        if response.status_code >= 400:
            raise RuntimeError(f"Vysočina announcement returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx, source_url=str(item.detail_url), content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        heading = soup.find("h1")
        title = _clean(heading.get_text(" ", strip=True)) if heading else (item.title_hint or item.external_id)
        main = soup.find("main") or soup
        body = _clean(main.get_text(" ", strip=True))
        opens, closes, window_text = _application_window(body)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                raw_fields={
                    "supportedActivitiesText": body[:15000],
                    "submissionWindowText": window_text,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "regionCode": "CZ063",
                    "regionName": "Kraj Vysočina",
                    "coverage": "LIMITED_OFFICIAL_ANNOUNCEMENTS",
                    "coverageNote": (
                        "Official Kraj Vysočina announcement index; protected "
                        "fondvysociny.cz catalogue is not bypassed."
                    ),
                    "discoveryMethod": item.metadata.get("discovery_method"),
                },
                artifacts=_artifacts(soup, str(item.detail_url)),
                snapshot_ids=[
                    item.metadata.get("discovery_snapshot_id"),
                    snapshot_id,
                ],
            ),
            http_status=response.status_code,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    async def fetch_artifact(
        self,
        ctx: AdapterContext,
        artifact: RemoteArtifactRef,
        validators: FetchValidators | None = None,
    ) -> ArtifactFetchResult:
        headers: dict[str, str] = {}
        if validators:
            if validators.etag:
                headers["if-none-match"] = validators.etag
            if validators.last_modified:
                headers["if-modified-since"] = validators.last_modified
        response = await ctx.http.get(str(artifact.url), headers=headers)
        if response.status_code == 304:
            return ArtifactFetchResult(state=FetchState.NOT_MODIFIED)
        if response.status_code == 404:
            return ArtifactFetchResult(state=FetchState.GONE)
        if response.status_code >= 400:
            raise RuntimeError(f"Vysočina artifact returned HTTP {response.status_code}")
        mime = response.headers.get(
            "content-type", artifact.mime_hint or "application/octet-stream"
        ).split(";", 1)[0]
        snapshot_id = self._snapshot(
            ctx, source_url=str(artifact.url), content=response.content,
            mime_type=mime, headers=response.headers,
        )
        return ArtifactFetchResult(
            state=FetchState.MODIFIED,
            snapshot_id=snapshot_id,
            sha256=hashlib.sha256(response.content).hexdigest(),
            mime_type=mime,
            size_bytes=len(response.content),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    def _snapshot(
        self,
        ctx: AdapterContext,
        *,
        source_url: str,
        content: bytes,
        mime_type: str,
        headers: Any,
    ) -> str:
        if ctx.snapshots is None:
            raise RuntimeError("Vysočina adapter requires ctx.snapshots")
        snapshot = ctx.snapshots.put(
            source_code=self.descriptor.code,
            source_url=source_url,
            content=content,
            mime_type=mime_type,
            retrieved_at=ctx.now,
            validators={
                "etag": headers.get("etag") or "",
                "last_modified": headers.get("last-modified") or "",
            },
        )
        return snapshot.snapshot_id
