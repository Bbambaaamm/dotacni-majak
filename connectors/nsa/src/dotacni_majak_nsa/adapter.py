from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
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


LISTING_URLS = (
    "https://nsa.gov.cz/dotace-investicni/",
    "https://nsa.gov.cz/dotace-neinvesticni/",
    "https://nsa.gov.cz/dotace-neinvesticni-parasport/",
)
_CALL_LINK_RE = re.compile(r"/dotace/(?:vyzva-|\d+_\d+|[^/]*vyzva[^/]*)", re.I)
_CALL_NUMBER_RE = re.compile(r"\b(?:Výzva\s*)?(\d{1,2})\s*/\s*(20\d{2})\b", re.I)
_MONEY_RE = re.compile(r"([0-9][0-9\s\u00a0]*)\s*Kč\b", re.I)
_LOCAL_TZ = ZoneInfo("Europe/Prague")


def _clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def _call_number(text: str, url: str) -> str:
    match = _CALL_NUMBER_RE.search(text)
    if match:
        return f"{int(match.group(1)):02d}/{match.group(2)}"

    slug = PurePosixPath(urlsplit(url).path.rstrip("/")).name
    slug_match = re.search(r"(\d{1,2})-(20\d{2})", slug)
    if slug_match:
        return f"{int(slug_match.group(1)):02d}/{slug_match.group(2)}"

    return slug


def _parse_local_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = _clean(value)
    for fmt in ("%d. %m. %Y, %H:%M hod.", "%d. %m. %Y, %H:%M", "%d. %m. %Y"):
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=_LOCAL_TZ)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _heading_value(soup: BeautifulSoup, label: str) -> str | None:
    label_norm = label.casefold()
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    for index, heading in enumerate(headings):
        if _clean(heading.get_text(" ", strip=True)).casefold() != label_norm:
            continue
        for candidate in headings[index + 1 :]:
            value = _clean(candidate.get_text(" ", strip=True))
            if value:
                return value
    return None


def _allocation_czk(text: str | None) -> int | None:
    if not text:
        return None
    match = _MONEY_RE.search(text)
    if not match:
        return None
    digits = re.sub(r"\s+", "", match.group(1).replace("\xa0", " "))
    try:
        return int(digits)
    except ValueError:
        return None


def _native_status(
    *,
    body_text: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    now: datetime,
) -> str:
    normalized = body_text.casefold()
    if "příjem žádostí byl ukončen" in normalized:
        return "CLOSED"
    current = now.astimezone(timezone.utc)
    if ends_at is not None and current > ends_at:
        return "CLOSED"
    if starts_at is not None and current < starts_at:
        return "PLANNED"
    if starts_at is not None or ends_at is not None:
        return "OPEN"
    return "UNKNOWN"


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.lower()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if path.endswith(".pptx"):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if path.endswith(".doc"):
        return "application/msword"
    return None


def _artifact_role(title: str) -> str:
    lowered = title.casefold()
    if "aktuální znění výzvy" in lowered or "aktualni zneni vyzvy" in lowered:
        return "CALL_DOCUMENT"
    if "návod" in lowered or "metodick" in lowered or "pokyn" in lowered:
        return "GUIDELINES"
    if "častější otáz" in lowered or "faq" in lowered:
        return "FAQ"
    if "přehled žádostí" in lowered or "rozhodnutí" in lowered:
        return "OTHER"
    return "ANNEX"


def _extract_artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    seen: set[str] = set()
    artifacts: list[RemoteArtifactRef] = []

    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if parsed.hostname not in {"nsa.gov.cz", "www.nsa.gov.cz"}:
            continue
        mime = _mime_hint(url)
        if mime is None and "/wp-content/uploads/" not in parsed.path:
            continue
        if url in seen:
            continue
        seen.add(url)

        title = _clean(anchor.get_text(" ", strip=True)) or PurePosixPath(parsed.path).name
        role = _artifact_role(title)
        external_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        artifacts.append(
            RemoteArtifactRef(
                external_id=external_id,
                url=url,
                role=role,
                title=title,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )

    return artifacts


def _description_text(soup: BeautifulSoup) -> str:
    paragraphs = []
    for p in soup.find_all("p"):
        text = _clean(p.get_text(" ", strip=True))
        if text and len(text) >= 40:
            paragraphs.append(text)
    return "\n".join(paragraphs[:12])


class NsaAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="NSA",
        name="Národní sportovní agentura",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://nsa.gov.cz/",
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF, RetrievalMode.DOCX, RetrievalMode.XLSX],
        allowed_hosts=["nsa.gov.cz", "www.nsa.gov.cz"],
        normal_refresh_minutes=360,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(LISTING_URLS[0])
            healthy = response.status_code == 200 and "Investiční výzvy" in response.text
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected HTTP/content: {response.status_code}"
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
        items_by_id: dict[str, DiscoveryItem] = {}

        for listing_url in LISTING_URLS:
            response = await ctx.http.get(listing_url)
            if response.status_code >= 400:
                raise RuntimeError(f"NSA listing returned HTTP {response.status_code}: {listing_url}")

            snapshot_id = self._snapshot(
                ctx,
                source_url=listing_url,
                content=response.content,
                mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
                headers=response.headers,
            )

            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                title = _clean(anchor.get_text(" ", strip=True))
                href = urljoin(listing_url, anchor["href"])
                if not title or "výzva" not in title.casefold():
                    continue
                parsed_href = urlsplit(href)
                if parsed_href.hostname not in {"nsa.gov.cz", "www.nsa.gov.cz"}:
                    continue
                if "/dotace/" not in parsed_href.path:
                    continue
                if not _CALL_LINK_RE.search(parsed_href.path):
                    continue

                external_id = _call_number(title, href)
                if not external_id:
                    continue

                existing = items_by_id.get(external_id)
                metadata = {
                    "listing_url": listing_url,
                    "listing_snapshot_id": snapshot_id,
                }
                item = DiscoveryItem(
                    external_id=external_id,
                    detail_url=href,
                    title_hint=title,
                    metadata=metadata,
                )
                if existing is None:
                    items_by_id[external_id] = item
                elif str(existing.detail_url) != href:
                    # Preserve ambiguity instead of silently merging two URLs.
                    items_by_id[f"{external_id}@{hashlib.sha256(href.encode()).hexdigest()[:8]}"] = item

        return DiscoveryPage(
            items=sorted(items_by_id.values(), key=lambda item: item.external_id),
            next_checkpoint=None,
            is_complete=True,
            total_hint=len(items_by_id),
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
            return RecordFetchResult(
                state=FetchState.NOT_MODIFIED,
                http_status=304,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
        if response.status_code == 404:
            return RecordFetchResult(state=FetchState.GONE, http_status=404)
        if response.status_code >= 400:
            raise RuntimeError(f"NSA detail returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        title = _clean(h1.get_text(" ", strip=True)) if h1 else (item.title_hint or item.external_id)
        body_text = _clean(soup.get_text(" ", strip=True))

        announced_text = _heading_value(soup, "DATUM VYHLÁŠENÍ VÝZVY")
        opens_text = _heading_value(soup, "ZAHÁJENÍ PŘÍJMU ŽÁDOSTÍ")
        closes_text = _heading_value(soup, "UKONČENÍ PŘÍJMU ŽÁDOSTÍ")
        allocation_text = _heading_value(soup, "ALOKACE")

        announced_at = _parse_local_datetime(announced_text)
        opens_at = _parse_local_datetime(opens_text)
        closes_at = _parse_local_datetime(closes_text)
        status = _native_status(
            body_text=body_text,
            starts_at=opens_at,
            ends_at=closes_at,
            now=ctx.now,
        )

        call_type = None
        type_match = re.search(
            r"Jedná se o\s+([^\.]{3,120}?)\s+Výzvu\.",
            body_text,
            flags=re.IGNORECASE,
        )
        if type_match:
            call_type = _clean(type_match.group(1))

        description = _description_text(soup)
        artifacts = _extract_artifacts(soup, str(item.detail_url))

        record = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title=title,
            native_status=status,
            published_at=announced_at,
            raw_fields={
                "announcedAt": announced_at.isoformat() if announced_at else None,
                "submissionOpenAt": opens_at.isoformat() if opens_at else None,
                "submissionCloseAt": closes_at.isoformat() if closes_at else None,
                "allocationCzk": _allocation_czk(allocation_text),
                "callType": call_type,
                "descriptionText": description,
                "explicitClosedText": "příjem žádostí byl ukončen" in body_text.casefold(),
            },
            artifacts=artifacts,
            snapshot_ids=[snapshot_id],
        )

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=record,
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
            return ArtifactFetchResult(
                state=FetchState.NOT_MODIFIED,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
        if response.status_code == 404:
            return ArtifactFetchResult(state=FetchState.GONE)
        if response.status_code >= 400:
            raise RuntimeError(f"NSA artifact returned HTTP {response.status_code}")

        mime = response.headers.get("content-type", artifact.mime_hint or "application/octet-stream").split(";", 1)[0]
        snapshot_id = self._snapshot(
            ctx,
            source_url=str(artifact.url),
            content=response.content,
            mime_type=mime,
            headers=response.headers,
        )
        digest = hashlib.sha256(response.content).hexdigest()
        return ArtifactFetchResult(
            state=FetchState.MODIFIED,
            snapshot_id=snapshot_id,
            sha256=digest,
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
            raise RuntimeError("NSA adapter requires ctx.snapshots for RAW-first ingestion")
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
