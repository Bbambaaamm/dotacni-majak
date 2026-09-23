from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

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

INDEX_URL = "https://www.kraj-jihocesky.cz/ku_dotace/vyhlasene"
_ALLOWED_HOSTS = {"www.kraj-jihocesky.cz", "kraj-jihocesky.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_HEADING_RE = re.compile(
    r"^Datum zveřejnění:\s*(\d{1,2}\.\d{1,2}\.20\d{2})\s+(.+)$",
    re.I,
)


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize(value)).strip("-")
    return normalized[:72] or "grant"


def _parse_date(value: str) -> datetime | None:
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(20\d{2})", value)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    return datetime(year, month, day, tzinfo=_LOCAL_TZ).astimezone(timezone.utc)


def _parse_harmonogram_datetime(text: str, label: str, *, closing: bool) -> datetime | None:
    folded = _normalize(text)
    wanted = _normalize(label)
    pos = folded.find(wanted)
    if pos < 0:
        return None
    snippet = text[pos:pos + 220]
    match = re.search(
        r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})"
        r"(?:\s+(?:od|do)\s+(\d{1,2})(?::(\d{2}))?\s*(?:hod(?:in)?\.?)?)?",
        snippet,
        re.I,
    )
    if not match:
        return None

    day, month, year = map(int, match.group(1, 2, 3))
    hour_raw = match.group(4)
    minute_raw = match.group(5)
    if hour_raw is None:
        local_time = time(23, 59, 59) if closing else time.min
    else:
        hour = int(hour_raw)
        minute = int(minute_raw or 0)
        if closing and hour == 24:
            local_time = time(23, 59, 59)
        else:
            local_time = time(min(hour, 23), minute)

    return datetime.combine(
        datetime(year, month, day).date(),
        local_time,
        tzinfo=_LOCAL_TZ,
    ).astimezone(timezone.utc)


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes and current > closes:
        return "CLOSED"
    if opens or closes:
        return "OPEN"
    return "UNKNOWN"


def _section_nodes(heading: Tag) -> list[Any]:
    nodes: list[Any] = []
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag) and sibling.name == "h2":
            break
        nodes.append(sibling)
    return nodes


def _section_text(nodes: list[Any]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, Tag):
            value = _clean(node.get_text(" ", strip=True))
        else:
            value = _clean(str(node))
        if value:
            parts.append(value)
    return _clean(" ".join(parts))


def _characteristic(nodes: list[Any]) -> str | None:
    collecting = False
    chunks: list[str] = []
    for node in nodes:
        if not isinstance(node, Tag):
            continue
        if node.name in {"h3", "h4", "h5"}:
            label = _normalize(_clean(node.get_text(" ", strip=True)))
            if label == "charakteristika":
                collecting = True
                continue
            if collecting:
                break
        if collecting:
            text = _clean(node.get_text(" ", strip=True))
            if text:
                chunks.append(text)
    value = _clean(" ".join(chunks))
    return value or None


def _application_url(nodes: list[Any], base_url: str) -> str | None:
    for node in nodes:
        if not isinstance(node, Tag):
            continue
        for anchor in node.find_all("a", href=True):
            label = _normalize(_clean(anchor.get_text(" ", strip=True)))
            if "priprava a odeslani zadosti" in label or "portal obcana" in label:
                return urljoin(base_url, anchor["href"])
    return None


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.casefold()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith((".doc", ".docx")):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.endswith((".xls", ".xlsx", ".xlsm")):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if path.endswith(".zip"):
        return "application/zip"
    return None


def _role(text: str) -> str:
    folded = _normalize(text)
    if "pravid" in folded or "podrobnosti" in folded:
        return "CALL_DOCUMENT"
    if "navod" in folded or "metodik" in folded:
        return "GUIDELINES"
    if "zadost" in folded or "formular" in folded:
        return "APPLICATION_FORM"
    return "ANNEX"


def _artifacts(nodes: list[Any], base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, Tag):
            continue
        for anchor in node.find_all("a", href=True):
            url = urljoin(base_url, anchor["href"])
            host = (urlsplit(url).hostname or "").lower()
            if host not in _ALLOWED_HOSTS or url in seen:
                continue
            mime = _mime_hint(url)
            label = _clean(anchor.get_text(" ", strip=True))
            if mime is None and "podrobnosti a tiskopisy" not in _normalize(label):
                continue
            seen.add(url)
            role = _role(label)
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


class JihoceskyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="JHC",
        name="Jihočeský kraj — vyhlášené dotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.kraj-jihocesky.cz/",
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
            response = await ctx.http.get(INDEX_URL)
            folded = _normalize(response.text)
            healthy = (
                response.status_code == 200
                and "dotace vyhlasene" in folded
                and "seznam dotaci" in folded
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Jihočeský grant index: HTTP {response.status_code}"
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
        response = await ctx.http.get(INDEX_URL)
        if response.status_code >= 400:
            raise RuntimeError(f"Jihočeský grant index returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=INDEX_URL,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        items: list[DiscoveryItem] = []

        for heading in soup.find_all("h2"):
            heading_text = _clean(heading.get_text(" ", strip=True))
            match = _HEADING_RE.match(heading_text)
            if not match:
                continue

            published_text, title = match.groups()
            published = _parse_date(published_text)
            nodes = _section_nodes(heading)
            body = _section_text(nodes)
            opens = _parse_harmonogram_datetime(body, "Datum vyhlášení:", closing=False)
            closes = _parse_harmonogram_datetime(body, "Datum ukončení:", closing=True)
            characteristic = _characteristic(nodes)
            app_url = _application_url(nodes, INDEX_URL)
            artifacts = _artifacts(nodes, INDEX_URL)

            identity_seed = f"{published_text}|{_normalize(title)}"
            digest = hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()[:12]
            external_id = f"JHC-{published.strftime('%Y%m%d') if published else 'unknown'}-{_slug(title)[:48]}-{digest}"

            items.append(
                DiscoveryItem(
                    external_id=external_id,
                    detail_url=f"{INDEX_URL}#{external_id.lower()}",
                    title_hint=title,
                    native_status_hint=_status(ctx.now, opens, closes),
                    published_at_hint=published,
                    metadata={
                        "source_snapshot_id": snapshot_id,
                        "published_at": published.isoformat() if published else None,
                        "submission_open_at": opens.isoformat() if opens else None,
                        "submission_close_at": closes.isoformat() if closes else None,
                        "characteristic": characteristic,
                        "application_url": app_url,
                        "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
                        "section_text": body[:12000],
                        "discovery_method": "official-html-active-grants-page",
                    },
                )
            )

        return DiscoveryPage(
            items=items,
            next_checkpoint=None,
            is_complete=True,
            total_hint=len(items),
        )

    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        del validators
        snapshot_id = item.metadata.get("source_snapshot_id")
        if not snapshot_id:
            raise RuntimeError("Jihočeský discovery item is missing RAW snapshot id")

        artifacts = [
            RemoteArtifactRef.model_validate(value)
            for value in item.metadata.get("artifacts", [])
        ]

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=item.title_hint,
                native_status=item.native_status_hint,
                published_at=item.published_at_hint,
                raw_fields={
                    "submissionOpenAt": item.metadata.get("submission_open_at"),
                    "submissionCloseAt": item.metadata.get("submission_close_at"),
                    "supportedActivitiesText": item.metadata.get("characteristic"),
                    "applicationUrl": item.metadata.get("application_url"),
                    "regionCode": "CZ031",
                    "regionName": "Jihočeský kraj",
                    "applicationWindowNotes": item.metadata.get("section_text"),
                    "discoveryMethod": item.metadata.get("discovery_method"),
                },
                artifacts=artifacts,
                snapshot_ids=[snapshot_id],
            ),
            http_status=200,
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
            raise RuntimeError(f"Jihočeský artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("Jihočeský adapter requires ctx.snapshots")
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
