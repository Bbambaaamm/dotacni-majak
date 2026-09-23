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


LISTING_URL = "https://opzp.cz/nabidka-dotaci"
_ALLOWED_HOSTS = {"opzp.cz", "www.opzp.cz", "2021-2027.opzp.cz"}
_DETAIL_LINK_RE = re.compile(r"^/dotace/(\d+)-vyzva/?$", re.I)
_CALL_NUMBER_RE = re.compile(r"\b(\d{1,3})\.\s*výzva\b", re.I)
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\s*[-–]\s*"
    r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})"
)
_MONEY_RE = re.compile(r"([0-9][0-9\s\u00a0]*)\s*Kč\b", re.I)
_LOCAL_TZ = ZoneInfo("Europe/Prague")


def _clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def _call_number(title: str, url: str) -> int | None:
    path_match = _DETAIL_LINK_RE.match(urlsplit(url).path)
    if path_match:
        return int(path_match.group(1))
    title_match = _CALL_NUMBER_RE.search(title)
    if title_match:
        return int(title_match.group(1))
    return None


def _title_from_anchor(anchor: Any) -> str:
    heading = anchor.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading is not None:
        title = _clean(heading.get_text(" ", strip=True))
        if title:
            return title

    text = _clean(anchor.get_text(" ", strip=True))
    marker = text.casefold().find("stav výzvy")
    if marker > 0:
        text = text[:marker].strip()
    return text


def _segment(text: str, label: str, next_labels: tuple[str, ...]) -> str | None:
    folded = text.casefold()
    label_folded = label.casefold()
    start = folded.find(label_folded)
    if start < 0:
        return None

    start += len(label_folded)
    remainder = text[start:].strip()
    remainder_folded = remainder.casefold()

    stops = [
        remainder_folded.find(candidate.casefold())
        for candidate in next_labels
        if remainder_folded.find(candidate.casefold()) >= 0
    ]
    if stops:
        remainder = remainder[: min(stops)].strip()

    return _clean(remainder) or None


def _parse_date_range(value: str | None) -> tuple[datetime | None, datetime | None]:
    if not value:
        return None, None

    match = _DATE_RANGE_RE.search(value)
    if not match:
        return None, None

    sd, sm, sy, ed, em, ey = (int(part) for part in match.groups())
    start = datetime(sy, sm, sd, tzinfo=_LOCAL_TZ)
    end = datetime.combine(
        datetime(ey, em, ed).date(),
        time.max,
        tzinfo=_LOCAL_TZ,
    )
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _allocation_czk(value: str | None) -> int | None:
    if not value:
        return None
    match = _MONEY_RE.search(value)
    if not match:
        return None
    digits = re.sub(r"\s+", "", match.group(1).replace("\xa0", " "))
    try:
        return int(digits)
    except ValueError:
        return None


def _native_status(
    status_text: str | None,
    *,
    opens_at: datetime | None,
    closes_at: datetime | None,
    now: datetime,
) -> str:
    normalized = (status_text or "").casefold()

    if "zruš" in normalized:
        return "CANCELLED"
    if "pozastav" in normalized:
        return "PAUSED"
    if "ukon" in normalized or "uzav" in normalized:
        return "CLOSED"
    if "plán" in normalized or "bude zahájen" in normalized:
        return "PLANNED"
    if "probíhá" in normalized or "otevřen" in normalized:
        return "OPEN"

    current = now.astimezone(timezone.utc)
    if opens_at and current < opens_at:
        return "PLANNED"
    if closes_at and current > closes_at:
        return "CLOSED"
    if opens_at or closes_at:
        return "OPEN"
    return "UNKNOWN"


def _description_text(soup: BeautifulSoup) -> str:
    paragraphs: list[str] = []
    for paragraph in soup.find_all("p"):
        text = _clean(paragraph.get_text(" ", strip=True))
        if len(text) < 40:
            continue
        lowered = text.casefold()
        if "cookies" in lowered or "přihlaste se k odběru" in lowered:
            continue
        paragraphs.append(text)
    return "\n".join(paragraphs[:8])


def _list_after_heading(soup: BeautifulSoup, label: str) -> list[str]:
    target = label.casefold()
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        if _clean(heading.get_text(" ", strip=True)).casefold() != target:
            continue

        values: list[str] = []
        for element in heading.find_all_next():
            if element is heading:
                continue
            if element.name and re.fullmatch(r"h[1-6]", element.name):
                break
            if element.name == "li":
                value = _clean(element.get_text(" ", strip=True))
                if value and value not in values:
                    values.append(value)
        return values
    return []


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.lower()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if path.endswith(".doc"):
        return "application/msword"
    return None


def _artifact_role(context: str) -> str:
    lowered = context.casefold()
    if "text výzvy" in lowered:
        return "CALL_DOCUMENT"
    if "pravidla pro žadatele" in lowered or "pržap" in lowered:
        return "GUIDELINES"
    if "faq" in lowered or "časté dotazy" in lowered:
        return "FAQ"
    if "formulář" in lowered or "žádost" in lowered:
        return "APPLICATION_FORM"
    return "ANNEX"


def _extract_artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    seen: set[str] = set()
    artifacts: list[RemoteArtifactRef] = []

    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if parsed.hostname not in _ALLOWED_HOSTS:
            continue

        mime = _mime_hint(url)
        if mime is None and "/files/documents/" not in parsed.path.lower():
            continue
        if url in seen:
            continue
        seen.add(url)

        parent_text = _clean(
            anchor.parent.get_text(" ", strip=True) if anchor.parent else ""
        )
        anchor_text = _clean(anchor.get_text(" ", strip=True))
        context = parent_text or anchor_text or PurePosixPath(parsed.path).name
        context = context[:220]
        role = _artifact_role(context)
        title = context or PurePosixPath(parsed.path).name
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


class OpzpAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="OPZP",
        name="Operační program Životní prostředí 2021–2027",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://opzp.cz/",
        retrieval_modes=[
            RetrievalMode.HTML,
            RetrievalMode.PDF,
            RetrievalMode.DOCX,
            RetrievalMode.XLSX,
        ],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=240,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(LISTING_URL)
            body = response.text.casefold()
            healthy = (
                response.status_code == 200
                and "nabídka dotací" in body
                and "výzva" in body
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else (
                f"Unexpected OPŽP listing response: HTTP {response.status_code}"
            )
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
        response = await ctx.http.get(LISTING_URL)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OPŽP listing returned HTTP {response.status_code}"
            )

        snapshot_id = self._snapshot(
            ctx,
            source_url=LISTING_URL,
            content=response.content,
            mime_type=response.headers.get(
                "content-type",
                "text/html",
            ).split(";", 1)[0],
            headers=response.headers,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        items_by_id: dict[str, DiscoveryItem] = {}

        for anchor in soup.find_all("a", href=True):
            href = urljoin(LISTING_URL, anchor["href"])
            parsed = urlsplit(href)
            if parsed.hostname not in _ALLOWED_HOSTS:
                continue

            path_match = _DETAIL_LINK_RE.match(parsed.path)
            if not path_match:
                continue

            title = _title_from_anchor(anchor)
            number = _call_number(title, href)
            if number is None:
                continue

            external_id = f"OPZP-{number}"
            item = DiscoveryItem(
                external_id=external_id,
                detail_url=href,
                title_hint=title or f"{number}. výzva",
                metadata={
                    "call_number": number,
                    "listing_snapshot_id": snapshot_id,
                },
            )

            existing = items_by_id.get(external_id)
            if existing is None:
                items_by_id[external_id] = item
            elif str(existing.detail_url) != href:
                ambiguity = hashlib.sha256(href.encode("utf-8")).hexdigest()[:8]
                items_by_id[f"{external_id}@{ambiguity}"] = item

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
            raise RuntimeError(
                f"OPŽP detail returned HTTP {response.status_code}"
            )

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get(
                "content-type",
                "text/html",
            ).split(";", 1)[0],
            headers=response.headers,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        title = (
            _clean(h1.get_text(" ", strip=True))
            if h1
            else (item.title_hint or item.external_id)
        )
        page_text = _clean(soup.get_text(" ", strip=True))

        status_text = _segment(
            page_text,
            "Stav výzvy",
            ("Druh výzvy", "Podání žádosti", "Alokace", "Popis"),
        )
        call_type = _segment(
            page_text,
            "Druh výzvy",
            ("Podání žádosti", "Alokace", "Popis"),
        )
        submission_text = _segment(
            page_text,
            "Podání žádosti",
            ("Alokace", "Podat žádost", "Správa žádostí", "Popis"),
        )
        allocation_text = _segment(
            page_text,
            "Alokace",
            ("Podat žádost", "Správa žádostí", "Popis"),
        )

        opens_at, closes_at = _parse_date_range(submission_text)
        native_status = _native_status(
            status_text,
            opens_at=opens_at,
            closes_at=closes_at,
            now=ctx.now,
        )

        applicants = _list_after_heading(soup, "Příjemci podpory")
        artifacts = _extract_artifacts(soup, str(item.detail_url))

        record = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title=title,
            native_status=native_status,
            raw_fields={
                "callNumber": item.metadata.get("call_number"),
                "officialStatusText": status_text,
                "callType": call_type,
                "submissionText": submission_text,
                "submissionOpenAt": (
                    opens_at.isoformat() if opens_at else None
                ),
                "submissionCloseAt": (
                    closes_at.isoformat() if closes_at else None
                ),
                "allocationCzk": _allocation_czk(allocation_text),
                "descriptionText": _description_text(soup),
                "applicants": applicants,
                "programme": "OPŽP 2021–2027",
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
            raise RuntimeError(
                f"OPŽP artifact returned HTTP {response.status_code}"
            )

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
            raise RuntimeError(
                "OPŽP adapter requires ctx.snapshots for RAW-first ingestion"
            )
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
