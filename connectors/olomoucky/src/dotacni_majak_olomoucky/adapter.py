from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit
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

CURRENT_URL = "https://www.olkraj.cz/dotace-granty-prispevky-krajske-dotacni-programy-2026/aktualni-dotacni-programy"
CLOSED_URL = "https://www.olkraj.cz/dotace-granty-prispevky-krajske-dotacni-programy-2026/ukoncene-dotacni-programy"
_ALLOWED_HOSTS = {"www.olkraj.cz", "olkraj.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_DETAIL_RE = re.compile(
    r"^/dotace-granty-prispevky-krajske-dotacni-programy-2026/"
    r"(?P<code>\d{2}-\d{2})-.+"
)


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _external_id(url: str) -> str:
    match = _DETAIL_RE.match(urlsplit(url).path)
    if match:
        return f"OLK-2026-{match.group('code').replace('-', '_')}"
    digest = hashlib.sha256(urlsplit(url).path.encode("utf-8")).hexdigest()[:12]
    return f"OLK-2026-{digest}"


def _table_value(soup: BeautifulSoup, label: str) -> str | None:
    wanted = _normalize(label)
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        left = _normalize(_clean(cells[0].get_text(" ", strip=True)))
        if left == wanted:
            return _clean(cells[1].get_text(" ", strip=True)) or None
    return None


def _table_link(soup: BeautifulSoup, label: str) -> str | None:
    wanted = _normalize(label)
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        left = _normalize(_clean(cells[0].get_text(" ", strip=True)))
        if left != wanted:
            continue
        anchor = cells[1].find("a", href=True)
        if anchor:
            return anchor["href"]
    return None


def _parse_deadline(value: str | None) -> tuple[datetime | None, datetime | None]:
    if not value:
        return None, None
    text = value.replace("\xa0", " ")

    full = re.search(
        r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\s*"
        r"(?:-|–|—)\s*"
        r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})"
        r"(?:\s*do\s*(\d{1,2}):(\d{2}))?",
        text,
        re.IGNORECASE,
    )
    if full:
        d1, m1, y1, d2, m2, y2, hh, mm = full.groups()
    else:
        short = re.search(
            r"(\d{1,2})\.\s*(\d{1,2})\.\s*"
            r"(?:-|–|—)\s*"
            r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})"
            r"(?:\s*do\s*(\d{1,2}):(\d{2}))?",
            text,
            re.IGNORECASE,
        )
        if not short:
            return None, None
        d1, m1, d2, m2, y2, hh, mm = short.groups()
        y1 = y2

    opens_local = datetime(int(y1), int(m1), int(d1), tzinfo=_LOCAL_TZ)
    closing_time = (
        time(int(hh), int(mm))
        if hh is not None
        else time(23, 59, 59)
    )
    closes_local = datetime(
        int(y2), int(m2), int(d2),
        closing_time.hour, closing_time.minute, closing_time.second,
        tzinfo=_LOCAL_TZ,
    )
    return (
        opens_local.astimezone(timezone.utc),
        closes_local.astimezone(timezone.utc),
    )


def _status(now: datetime, opens: datetime | None, closes: datetime | None, *, closed_index: bool) -> str:
    if closed_index:
        return "CLOSED"
    if opens is None or closes is None:
        return "UNKNOWN"
    current = now.astimezone(timezone.utc)
    if current < opens:
        return "PLANNED"
    if current > closes:
        return "CLOSED"
    return "OPEN"


def _documents(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        path = parsed.path.casefold()
        if not path.endswith((".pdf", ".doc", ".docx", ".odt", ".xls", ".xlsx", ".zip")):
            continue
        if url in seen:
            continue
        seen.add(url)

        label = _clean(anchor.get_text(" ", strip=True))
        folded = _normalize(label)
        role = (
            "CALL_DOCUMENT"
            if "pravid" in folded
            else "APPLICATION_FORM"
            if "zadost" in folded and "vzor" in folded
            else "ANNEX"
        )
        mime = (
            "application/pdf" if path.endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if path.endswith((".doc", ".docx", ".odt"))
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if path.endswith((".xls", ".xlsx"))
            else "application/zip"
        )
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=label[:500] or url,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


def _discovery_links(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str]]:
    result: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        if not _DETAIL_RE.match(parsed.path):
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        result[url] = label or parsed.path.rsplit("/", 1)[-1]
    return sorted(result.items())


class OlomouckyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="OLK",
        name="Olomoucký kraj — krajské dotační programy 2026",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.olkraj.cz/",
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF, RetrievalMode.DOCX, RetrievalMode.XLSX],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=180,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(CURRENT_URL)
            folded = _normalize(response.text)
            healthy = (
                response.status_code == 200
                and "aktualni dotacni programy" in folded
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Olomoucký current programmes page: HTTP {response.status_code}"
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
        items: dict[str, DiscoveryItem] = {}
        for index_url, closed_index in ((CURRENT_URL, False), (CLOSED_URL, True)):
            response = await ctx.http.get(index_url)
            if response.status_code >= 400:
                continue
            snapshot_id = self._snapshot(
                ctx,
                source_url=index_url,
                content=response.content,
                mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
                headers=response.headers,
            )
            soup = BeautifulSoup(response.text, "html.parser")
            for url, title in _discovery_links(soup, index_url):
                ext = _external_id(url)
                existing = items.get(ext)
                metadata = {
                    "discovery_snapshot_id": snapshot_id,
                    "discovery_method": "official-current-or-closed-index",
                    "closed_index": closed_index,
                }
                # Current index wins if the same program appears on both pages.
                if existing is None or (existing.metadata.get("closed_index") and not closed_index):
                    items[ext] = DiscoveryItem(
                        external_id=ext,
                        detail_url=url,
                        title_hint=title,
                        metadata=metadata,
                    )

        values = sorted(items.values(), key=lambda item: item.external_id)
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
            raise RuntimeError(f"Olomoucký grant detail returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        table_name = _table_value(soup, "Název")
        heading = soup.find("h1")
        title = table_name or (
            _clean(heading.get_text(" ", strip=True))
            if heading
            else (item.title_hint or item.external_id)
        )
        deadline_text = _table_value(soup, "Termín příjmu žádostí")
        opens, closes = _parse_deadline(deadline_text)
        closed_index = bool(item.metadata.get("closed_index"))
        app_href = _table_link(soup, "RAP – podání žádosti")
        app_url = urljoin(str(item.detail_url), app_href) if app_href else None

        code_match = re.match(r"\s*(\d{2})[_-](\d{2})", title)
        code = f"{code_match.group(1)}_{code_match.group(2)}" if code_match else None

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes, closed_index=closed_index),
                raw_fields={
                    "sourceCallCode": code,
                    "programme": "Olomoucký kraj — krajské dotační programy 2026",
                    "annotationText": _table_value(soup, "Anotace"),
                    "eligibleApplicantsText": _table_value(soup, "Oprávnění žadatelé"),
                    "deadlineText": deadline_text,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "applicationUrl": app_url,
                    "regionCode": "CZ071",
                    "regionName": "Olomoucký kraj",
                    "discoveryMethod": item.metadata.get("discovery_method"),
                    "discoveredAsClosed": closed_index,
                },
                artifacts=_documents(soup, str(item.detail_url)),
                snapshot_ids=[snapshot_id],
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
            raise RuntimeError(f"Olomoucký grant artifact returned HTTP {response.status_code}")

        mime = response.headers.get(
            "content-type",
            artifact.mime_hint or "application/octet-stream",
        ).split(";", 1)[0]
        snapshot_id = self._snapshot(
            ctx,
            source_url=str(artifact.url),
            content=response.content,
            mime_type=mime,
            headers=response.headers,
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
            raise RuntimeError("Olomoucký adapter requires ctx.snapshots")
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
