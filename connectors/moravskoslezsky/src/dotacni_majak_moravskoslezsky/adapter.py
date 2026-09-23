from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from pathlib import PurePosixPath
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

ROOT_URL = "https://www.msk.cz/cs/temata/dotace/"
_ALLOWED_HOSTS = {"www.msk.cz", "msk.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_DETAIL_PATH_RE = re.compile(r"^/cs/temata/dotace/.+-([0-9]+)/?$")
_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.\s*(?P<year>20\d{2})"
    r"(?:\s*(?:od\s*)?(?P<hour>\d{1,2})[:.]?(?P<minute>\d{2})?\s*(?:hod\.?|h)?)?",
    re.IGNORECASE,
)
_CODE_RE = re.compile(
    r"(?:Kód programu|Název programu \(kód\))\s*:?\s*([^\n\r]{2,80})",
    re.IGNORECASE,
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
    path = urlsplit(url).path
    match = _DETAIL_PATH_RE.match(path)
    if match:
        return f"MSK-{match.group(1)}"
    slug = PurePosixPath(path.rstrip("/")).name
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    return f"MSK-{slug[:48]}-{digest}"


def _deadline_text(soup: BeautifulSoup) -> str | None:
    candidates: list[str] = []
    for element in soup.find_all(["p", "div", "li"]):
        text = _clean(element.get_text(" ", strip=True))
        folded = _normalize(text)
        if (
            "lhuta pro pod" in folded
            or "termin podani" in folded
            or "termin pro podani" in folded
        ):
            if len(text) <= 1000:
                candidates.append(text)
    if not candidates:
        return None
    return min(candidates, key=len)


def _parse_deadline_range(value: str | None) -> tuple[datetime | None, datetime | None]:
    if not value:
        return None, None
    matches = list(_DATE_RE.finditer(value))
    # Multiple rounds are intentionally not collapsed into a fake continuous
    # interval. The raw deadline text remains available for later modelling.
    if len(matches) != 2:
        return None, None

    parsed: list[datetime] = []
    for index, match in enumerate(matches):
        hour_raw = match.group("hour")
        minute_raw = match.group("minute")
        if hour_raw is None:
            local_time = time(23, 59, 59) if index == 1 else time.min
        else:
            local_time = time(int(hour_raw), int(minute_raw or 0))
        local = datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            local_time.hour,
            local_time.minute,
            local_time.second,
            tzinfo=_LOCAL_TZ,
        )
        parsed.append(local.astimezone(timezone.utc))
    return parsed[0], parsed[1]


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    current = now.astimezone(timezone.utc)
    if opens is None or closes is None:
        return "UNKNOWN"
    if current < opens:
        return "PLANNED"
    if current > closes:
        return "CLOSED"
    return "OPEN"


def _programme_code(soup: BeautifulSoup) -> str | None:
    text = soup.get_text("\n", strip=True)
    match = _CODE_RE.search(text)
    if not match:
        return None
    code = _clean(match.group(1))
    # Prevent accidentally capturing an entire following sentence.
    return code.split("Rada kraje", 1)[0].strip(" .")[:80] or None


def _application_url(soup: BeautifulSoup, base_url: str) -> str | None:
    for anchor in soup.find_all("a", href=True):
        label = _normalize(_clean(anchor.get_text(" ", strip=True)))
        if "e-podani" in label or "epodani" in label:
            return urljoin(base_url, anchor["href"])
    return None


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True))
        folded = _normalize(label)
        if not any(
            marker in folded
            for marker in ("podmink", "priloha", "zadost", "vyuctovan", "smlouv")
        ):
            continue
        url = urljoin(base_url, anchor["href"])
        host = (urlsplit(url).hostname or "").lower()
        if host not in _ALLOWED_HOSTS or url in seen:
            continue
        seen.add(url)
        path = urlsplit(url).path.casefold()
        if path.endswith(".pdf"):
            mime = "application/pdf"
        elif path.endswith((".doc", ".docx", ".odt")):
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif path.endswith((".xls", ".xlsx", ".xlsm")):
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            mime = "text/html"

        role = (
            "CALL_DOCUMENT"
            if "podmink" in folded
            else "APPLICATION_FORM"
            if "zadost" in folded
            else "ANNEX"
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


def _discovery_links(soup: BeautifulSoup, page_url: str) -> tuple[list[tuple[str, str]], list[str]]:
    details: dict[str, str] = {}
    pages: set[str] = set()
    root_path = urlsplit(ROOT_URL).path.rstrip("/")

    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"])
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if host not in _ALLOWED_HOSTS:
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        if _DETAIL_PATH_RE.match(parsed.path):
            if label:
                details[url] = label
            continue
        if parsed.path.rstrip("/") == root_path and parsed.query:
            folded = _normalize(label)
            if folded.isdigit() or any(x in folded for x in ("dalsi", "nasledujici")):
                pages.add(url)

    return sorted(details.items()), sorted(pages)


class MoravskoslezskyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="MSK",
        name="Moravskoslezský kraj — dotační programy",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.msk.cz/",
        retrieval_modes=[
            RetrievalMode.HTML,
            RetrievalMode.PDF,
            RetrievalMode.DOCX,
            RetrievalMode.XLSX,
        ],
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
            response = await ctx.http.get(ROOT_URL)
            folded = _normalize(response.text)
            healthy = response.status_code == 200 and "dotace" in folded
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected MSK dotace index: HTTP {response.status_code}"
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
        queue = [ROOT_URL]
        visited: set[str] = set()
        items: dict[str, DiscoveryItem] = {}

        while queue and len(visited) < 20:
            page_url = queue.pop(0)
            if page_url in visited:
                continue
            visited.add(page_url)

            response = await ctx.http.get(page_url)
            if response.status_code >= 400:
                continue
            snapshot_id = self._snapshot(
                ctx,
                source_url=page_url,
                content=response.content,
                mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
                headers=response.headers,
            )
            soup = BeautifulSoup(response.text, "html.parser")
            details, pages = _discovery_links(soup, page_url)
            for url, title in details:
                ext = _external_id(url)
                items[ext] = DiscoveryItem(
                    external_id=ext,
                    detail_url=url,
                    title_hint=title,
                    metadata={
                        "discovery_snapshot_id": snapshot_id,
                        "discovery_method": "official-dotace-topic-index",
                    },
                )
            for url in pages:
                if url not in visited and url not in queue:
                    queue.append(url)

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
            raise RuntimeError(f"MSK grant detail returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        heading = soup.find("h1")
        title = _clean(heading.get_text(" ", strip=True)) if heading else (item.title_hint or item.external_id)
        deadline = _deadline_text(soup)
        opens, closes = _parse_deadline_range(deadline)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                raw_fields={
                    "sourceCallCode": _programme_code(soup),
                    "programme": "Moravskoslezský kraj — dotační programy",
                    "deadlineText": deadline,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "applicationUrl": _application_url(soup, str(item.detail_url)),
                    "regionCode": "CZ080",
                    "regionName": "Moravskoslezský kraj",
                    "discoveryMethod": item.metadata.get("discovery_method"),
                },
                artifacts=_artifacts(soup, str(item.detail_url)),
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
            raise RuntimeError(f"MSK grant artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("MSK adapter requires ctx.snapshots")
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
