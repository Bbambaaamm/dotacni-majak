from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
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

AREAS_URL = "https://dotace.kr-jihomoravsky.cz/Oblasti.aspx"
_ALLOWED_HOSTS = {"dotace.kr-jihomoravsky.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_FOLDER_RE = re.compile(r"^/Folders/\d+-\d+-.+\.aspx$", re.IGNORECASE)
_GRANT_RE = re.compile(r"^/Grants/(?P<id>\d+)-\d+-.+\.aspx$", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(?P<d>\d{1,2})\.\s*(?P<m>\d{1,2})\.\s*(?P<y>20\d{2})\b")
_TIME_RE = re.compile(r"\b(?P<h>\d{1,2})[:.](?P<mi>\d{2})\b")


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _external_id(url: str) -> str:
    match = _GRANT_RE.match(urlsplit(url).path)
    if not match:
        raise ValueError(f"not a JMK grant URL: {url}")
    return f"JMK-{match.group('id')}"


def _label_value(soup: BeautifulSoup, label: str) -> str | None:
    wanted = _normalize(label)
    # The legacy portal renders fields in various table/div structures.
    for element in soup.find_all(["th", "td", "strong", "b", "span", "div", "p"]):
        own = _normalize(_clean(element.get_text(" ", strip=True)))
        if not own.startswith(wanted):
            continue

        text = _clean(element.get_text(" ", strip=True))
        if ":" in text:
            left, right = text.split(":", 1)
            if _normalize(left).startswith(wanted) and right.strip():
                return right.strip()

        parent = element.parent
        if parent is not None:
            cells = parent.find_all(["th", "td"], recursive=False)
            if len(cells) >= 2:
                left = _normalize(_clean(cells[0].get_text(" ", strip=True)))
                if left.startswith(wanted):
                    return _clean(cells[1].get_text(" ", strip=True)) or None

        sibling = element.find_next_sibling()
        if sibling is not None:
            value = _clean(sibling.get_text(" ", strip=True))
            if value:
                return value
    return None


def _extract_by_text(soup: BeautifulSoup, label: str) -> str | None:
    value = _label_value(soup, label)
    if value:
        return value
    text = soup.get_text("\n", strip=True)
    pattern = re.compile(
        rf"{re.escape(label)}\s*:?\s*([^\n\r]+)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return _clean(match.group(1)) if match else None


def _parse_range(value: str | None) -> tuple[datetime | None, datetime | None]:
    if not value:
        return None, None
    matches = list(_DATE_RE.finditer(value))
    if len(matches) < 2:
        return None, None

    parsed: list[datetime] = []
    for index, match in enumerate((matches[0], matches[-1])):
        segment_end = (
            matches[-1].start()
            if index == 0
            else len(value)
        )
        segment = value[match.end():segment_end]
        tm = _TIME_RE.search(segment)
        if tm:
            local_time = time(int(tm.group("h")), int(tm.group("mi")))
        else:
            local_time = time.min if index == 0 else time(23, 59, 59)
        local = datetime(
            int(match.group("y")),
            int(match.group("m")),
            int(match.group("d")),
            local_time.hour,
            local_time.minute,
            local_time.second,
            tzinfo=_LOCAL_TZ,
        )
        parsed.append(local.astimezone(timezone.utc))
    return parsed[0], parsed[1]


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
    folded = _normalize(value)
    if "nezverej" in folded or "neni stanov" in folded or "viz" in folded:
        return None
    normalized = (
        value.replace("\xa0", " ")
        .replace(".000", "000")
        .replace(" ", "")
        .replace(",-", "")
        .replace(",", ".")
    )
    match = re.search(r"(\d+(?:\.\d+)?)", normalized)
    if not match:
        return None
    try:
        crowns = Decimal(match.group(1))
    except InvalidOperation:
        return None
    return int(crowns * 100)


def _percent_bps(value: str | None) -> int | None:
    if not value:
        return None
    folded = _normalize(value)
    if "neni pozad" in folded or "neni stanov" in folded:
        return 0
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*%", value)
    if len(matches) != 1:
        return None
    try:
        return int(Decimal(matches[0].replace(",", ".")) * 100)
    except InvalidOperation:
        return None


def _documents(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if (urlsplit(url).hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        path = urlsplit(url).path.casefold()
        label = _clean(anchor.get_text(" ", strip=True))
        folded = _normalize(label)
        if url in seen:
            continue
        if not (
            path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".fo", ".zip"))
            or any(word in folded for word in ("dokument", "zadost", "pravid", "rozpoc"))
        ):
            continue
        seen.add(url)
        role = (
            "CALL_DOCUMENT"
            if "program" in folded or "pravid" in folded
            else "APPLICATION_FORM"
            if "zadost" in folded or path.endswith(".fo")
            else "ANNEX"
        )
        mime = (
            "application/pdf" if path.endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if path.endswith((".doc", ".docx"))
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if path.endswith((".xls", ".xlsx"))
            else "application/octet-stream"
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


def _folder_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() in _ALLOWED_HOSTS and _FOLDER_RE.match(parsed.path):
            urls.add(url)
    return sorted(urls)


def _grant_links(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str]]:
    rows: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS or not _GRANT_RE.match(parsed.path):
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        rows[url] = label or parsed.path.rsplit("/", 1)[-1]
    return sorted(rows.items())


class JihomoravskyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="JMK",
        name="Jihomoravský kraj — dotační portál",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://dotace.kr-jihomoravsky.cz/",
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
            response = await ctx.http.get(AREAS_URL)
            folded = _normalize(response.text)
            healthy = response.status_code == 200 and "dotacni oblasti" in folded
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected JMK areas page: HTTP {response.status_code}"
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
        root = await ctx.http.get(AREAS_URL)
        if root.status_code >= 400:
            raise RuntimeError(f"JMK areas page returned HTTP {root.status_code}")
        root_snapshot = self._snapshot(
            ctx,
            source_url=AREAS_URL,
            content=root.content,
            mime_type=root.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=root.headers,
        )
        area_soup = BeautifulSoup(root.text, "html.parser")
        items: dict[str, DiscoveryItem] = {}

        for folder_url in _folder_links(area_soup, AREAS_URL):
            response = await ctx.http.get(folder_url)
            if response.status_code >= 400:
                continue
            folder_snapshot = self._snapshot(
                ctx,
                source_url=folder_url,
                content=response.content,
                mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
                headers=response.headers,
            )
            soup = BeautifulSoup(response.text, "html.parser")
            for url, title in _grant_links(soup, folder_url):
                ext = _external_id(url)
                items[ext] = DiscoveryItem(
                    external_id=ext,
                    detail_url=url,
                    title_hint=title,
                    metadata={
                        "root_snapshot_id": root_snapshot,
                        "discovery_snapshot_id": folder_snapshot,
                        "discovery_folder": folder_url,
                        "discovery_method": "official-area-folder",
                    },
                )

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
            raise RuntimeError(f"JMK grant detail returned HTTP {response.status_code}")

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

        deadline_text = _extract_by_text(soup, "Příjem žádostí")
        opens, closes = _parse_range(deadline_text)
        allocation_text = _extract_by_text(soup, "Objem finančních prostředků vyčleněných na program")
        purpose = _extract_by_text(soup, "Cíl/učel programu")
        location = _extract_by_text(soup, "Územní lokalizace programu")
        recipients = _extract_by_text(soup, "Příjemci podpory")
        min_support_text = _extract_by_text(soup, "Minimální výše podpory na jeden projekt/akci/činnost")
        max_support_text = _extract_by_text(soup, "Maximální výše podpory na jeden projekt/akci/činnost")
        cofinancing_text = _extract_by_text(soup, "Minimální podíl spoluúčasti žadatele")
        approved_at = _extract_by_text(soup, "Datum schválení")
        resolution = _extract_by_text(soup, "Číslo usnesení")

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                raw_fields={
                    "programme": "Jihomoravský kraj — dotační portál",
                    "purposeText": purpose,
                    "locationText": location,
                    "eligibleApplicantsText": recipients,
                    "deadlineText": deadline_text,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "totalAllocationMinor": _money_minor(allocation_text),
                    "allocationText": allocation_text,
                    "grantAmountMinMinor": _money_minor(min_support_text),
                    "grantAmountMaxMinor": _money_minor(max_support_text),
                    "ownContributionMinBps": _percent_bps(cofinancing_text),
                    "ownContributionText": cofinancing_text,
                    "approvedAtText": approved_at,
                    "resolutionText": resolution,
                    "regionCode": "CZ064",
                    "regionName": "Jihomoravský kraj",
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
            raise RuntimeError(f"JMK artifact returned HTTP {response.status_code}")
        mime = response.headers.get("content-type", artifact.mime_hint or "application/octet-stream").split(";", 1)[0]
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
            raise RuntimeError("JMK adapter requires ctx.snapshots")
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
