from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
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

ROOT_URL = "https://zlinskykraj.cz/dotace"
_ALLOWED_HOSTS = {"zlinskykraj.cz", "www.zlinskykraj.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_CODE_RE = re.compile(r"\b([A-Z]{2,6}\d{2}-\d{2})\b")
_DATE_RE = r"(\d{1,2}\.\d{1,2}\.20\d{2})"


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _programme_code(value: str | None) -> str | None:
    if not value:
        return None
    match = _CODE_RE.search(value)
    return match.group(1) if match else None


def _external_id(url: str, title: str | None = None) -> str:
    code = _programme_code(title)
    if code:
        return f"ZLK-{code}"
    path = urlsplit(url).path.rstrip("/")
    slug = PurePosixPath(path).name
    slug_code = _programme_code(slug.upper())
    if slug_code:
        return f"ZLK-{slug_code}"
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    return f"ZLK-{slug[:48]}-{digest}"


def _parse_date(value: str | None, *, closing: bool = False) -> datetime | None:
    if not value:
        return None
    match = re.search(_DATE_RE, value)
    if not match:
        return None
    day, month, year = map(int, match.group(1).split("."))
    local_time = time(23, 59, 59) if closing else time.min
    return datetime(
        year, month, day,
        local_time.hour, local_time.minute, local_time.second,
        tzinfo=_LOCAL_TZ,
    ).astimezone(timezone.utc)


def _field(text: str, label_pattern: str) -> str | None:
    match = re.search(
        rf"{label_pattern}\s*:?\s*([^\n\r]+)",
        text,
        re.IGNORECASE,
    )
    return _clean(match.group(1)) if match else None


def _submission_range(text: str) -> tuple[datetime | None, datetime | None, str | None]:
    match = re.search(
        rf"Příjem\s+žádosti\s+dotačního\s+programu\s*:?\s*{_DATE_RE}\s*(?:->|–|—|-)\s*{_DATE_RE}",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None, None
    raw = _clean(match.group(0))
    return _parse_date(match.group(1)), _parse_date(match.group(2), closing=True), raw


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    if opens is None or closes is None:
        return "UNKNOWN"
    current = now.astimezone(timezone.utc)
    if current < opens:
        return "PLANNED"
    if current > closes:
        return "CLOSED"
    return "OPEN"


def _money_minor(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.replace("\xa0", " ").replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(mil\.?|tis\.?)?\s*(?:Kč|CZK)", normalized, re.IGNORECASE)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation:
        return None
    multiplier = Decimal(1)
    unit = (match.group(2) or "").casefold()
    if unit.startswith("mil"):
        multiplier = Decimal(1_000_000)
    elif unit.startswith("tis"):
        multiplier = Decimal(1_000)
    crowns = amount * multiplier
    return int(crowns * 100)


def _documents(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    allowed_ext = (".pdf", ".doc", ".docx", ".odt", ".xls", ".xlsx", ".xlsm", ".zip")
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        if not parsed.path.casefold().endswith(allowed_ext) or url in seen:
            continue
        seen.add(url)
        label = _clean(anchor.get_text(" ", strip=True))
        folded = _normalize(label)
        role = (
            "CALL_DOCUMENT"
            if "program" in folded and "podporen" not in folded
            else "APPLICATION_FORM"
            if "zadost" in folded
            else "ANNEX"
        )
        mime = (
            "application/pdf" if parsed.path.casefold().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if parsed.path.casefold().endswith((".doc", ".docx", ".odt"))
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if parsed.path.casefold().endswith((".xls", ".xlsx", ".xlsm"))
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


def _application_url(soup: BeautifulSoup, base_url: str) -> str | None:
    for anchor in soup.find_all("a", href=True):
        parent_text = _normalize(_clean(anchor.parent.get_text(" ", strip=True) if anchor.parent else anchor.get_text(" ", strip=True)))
        if "odkaz na zadost" in parent_text or "zadost o dotaci" in parent_text:
            url = urljoin(base_url, anchor["href"])
            if urlsplit(url).scheme in {"http", "https"}:
                return url
    return None


def _discovery_links(soup: BeautifulSoup, page_url: str) -> tuple[list[tuple[str, str]], list[str]]:
    details: dict[str, str] = {}
    pages: set[str] = set()
    root_path = urlsplit(ROOT_URL).path.rstrip("/")
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        if parsed.path.startswith(root_path + "/") and parsed.path.rstrip("/") != root_path:
            if _programme_code(label) or _programme_code(PurePosixPath(parsed.path).name.upper()):
                details[url] = label or PurePosixPath(parsed.path).name
            continue
        if parsed.path.rstrip("/") == root_path and parsed.query:
            folded = _normalize(label)
            if folded.isdigit() or any(x in folded for x in ("dalsi", "nasledujici")):
                pages.add(url)
    return sorted(details.items()), sorted(pages)


class ZlinskyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="ZLK",
        name="Zlínský kraj — dotační programy",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://zlinskykraj.cz/",
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
            response = await ctx.http.get(ROOT_URL)
            folded = _normalize(response.text)
            healthy = response.status_code == 200 and "dotace" in folded
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Zlínský dotace index: HTTP {response.status_code}"
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

    async def discover(self, ctx: AdapterContext, checkpoint: SourceCheckpoint | None) -> DiscoveryPage:
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
                ext = _external_id(url, title)
                items[ext] = DiscoveryItem(
                    external_id=ext,
                    detail_url=url,
                    title_hint=title,
                    metadata={
                        "discovery_snapshot_id": snapshot_id,
                        "discovery_method": "official-dotace-index",
                    },
                )
            for url in pages:
                if url not in visited and url not in queue:
                    queue.append(url)

        values = sorted(items.values(), key=lambda item: item.external_id)
        return DiscoveryPage(items=values, next_checkpoint=None, is_complete=True, total_hint=len(values))

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
            raise RuntimeError(f"Zlínský grant detail returned HTTP {response.status_code}")

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
        text = soup.get_text("\n", strip=True)
        opens, closes, deadline_text = _submission_range(text)
        allocation_text = _field(text, r"Finanční\s+alokace")
        area = _field(text, r"Oblast\s*\(sekce\)\s*dotace")
        announced = _parse_date(_field(text, r"Termín\s+vyhlášení\s+programu"))

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                raw_fields={
                    "sourceCallCode": _programme_code(title),
                    "programme": "Zlínský kraj — dotační programy",
                    "announcedAt": announced.isoformat() if announced else None,
                    "deadlineText": deadline_text,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "totalAllocationMinor": _money_minor(allocation_text),
                    "allocationText": allocation_text,
                    "grantAreaText": area,
                    "applicationUrl": _application_url(soup, str(item.detail_url)),
                    "regionCode": "CZ072",
                    "regionName": "Zlínský kraj",
                    "discoveryMethod": item.metadata.get("discovery_method"),
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
            raise RuntimeError(f"Zlínský grant artifact returned HTTP {response.status_code}")

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

    def _snapshot(self, ctx: AdapterContext, *, source_url: str, content: bytes, mime_type: str, headers: Any) -> str:
        if ctx.snapshots is None:
            raise RuntimeError("Zlínský adapter requires ctx.snapshots")
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
