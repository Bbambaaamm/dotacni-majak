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

INDEX_URL = "https://dotace.pardubickykraj.cz/grants"
_ALLOWED_HOSTS = {"dotace.pardubickykraj.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_DETAIL_RE = re.compile(
    r"^/grants/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$",
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


def _date(
    value: str | None,
    *,
    closing: bool = False,
    hour: int | None = None,
    minute: int = 0,
) -> datetime | None:
    if not value:
        return None
    match = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b", value)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    if hour is not None:
        local_time = time(hour, minute)
    else:
        local_time = time(23, 59, 59) if closing else time.min
    return datetime.combine(
        datetime(year, month, day).date(),
        local_time,
        tzinfo=_LOCAL_TZ,
    ).astimezone(timezone.utc)


def _status(now: datetime, opens: datetime | None, closes: datetime | None, body: str = "") -> str:
    folded = _normalize(body)
    if "prijem zadosti pozastaven" in folded:
        return "PAUSED"
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes and current > closes:
        return "CLOSED"
    if "prijem zadosti ukoncen" in folded or "vyzva uzavrena" in folded:
        return "CLOSED"
    if opens or closes:
        return "OPEN"
    return "UNKNOWN"


def _money_minor(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.replace("\xa0", " ")
    match = re.search(r"([0-9][0-9 .]*)\s*(?:Kč|,-?\s*Kč)", normalized, re.I)
    if not match:
        return None
    digits = re.sub(r"[^0-9]", "", match.group(1))
    return int(digits) * 100 if digits else None


def _percent_bps(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*%", value)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    return int(round(number * 100))


def _detail_links(soup: BeautifulSoup) -> list[tuple[str, str, str]]:
    """Return (url, title, card_text) from public program cards."""
    result: dict[str, tuple[str, str]] = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(INDEX_URL, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        if not _DETAIL_RE.match(parsed.path.rstrip("/") or "/"):
            continue

        card = anchor.find_parent(["article", "li", "div"])
        card_text = _clean(card.get_text(" ", strip=True)) if card else ""
        label = _clean(anchor.get_text(" ", strip=True))
        if _normalize(label) in {"prejit na detail", "detail"}:
            heading = card.find(["h2", "h3", "h4", "h5", "h6"]) if card else None
            label = _clean(heading.get_text(" ", strip=True)) if heading else ""
        if not label:
            label = card_text[:500]
        result[url] = (label, card_text)

    return [(url, title, text) for url, (title, text) in sorted(result.items())]


def _card_dates(card_text: str) -> tuple[datetime | None, datetime | None]:
    match = re.search(
        r"\bod\s+(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"\s+do\s+(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
        card_text,
        re.I,
    )
    if not match:
        return None, None
    return _date(match.group(1)), _date(match.group(2), closing=True)


def _body_text(soup: BeautifulSoup) -> str:
    main = soup.find("main") or soup
    return _clean(main.get_text(" ", strip=True))


def _labeled_paragraph(body: str, label: str, *, stop_labels: tuple[str, ...] = ()) -> str | None:
    folded = _normalize(body)
    wanted = _normalize(label)
    pos = folded.find(wanted)
    if pos < 0:
        return None
    start = pos + len(label)
    end = len(body)
    for stop in stop_labels:
        stop_pos = folded.find(_normalize(stop), start)
        if stop_pos >= 0:
            end = min(end, stop_pos)
    value = _clean(body[start:end].lstrip(" :"))
    return value or None


def _application_window(body: str) -> tuple[datetime | None, datetime | None]:
    folded = _normalize(body)
    patterns = (
        r"termin\s+pro\s+predkladani\s+zadosti[^:]*:\s*"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"\s*[–-]\s*"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"(?:\s+(\d{1,2}):(\d{2}))?",
        r"zadosti[^.]{0,100}?od\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"\s+do\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"(?:\s+(\d{1,2}):(\d{2}))?",
    )
    for pattern in patterns:
        match = re.search(pattern, folded, re.I)
        if not match:
            continue
        hour = int(match.group(3)) if match.group(3) is not None else None
        minute = int(match.group(4) or 0)
        return (
            _date(match.group(1)),
            _date(match.group(2), closing=hour is None, hour=hour, minute=minute),
        )
    return None, None


def _grant_range(body: str) -> tuple[int | None, int | None]:
    match = re.search(
        r"minimalni\s+a\s+maximalni\s+vyse\s+dotace\s*:\s*"
        r"([^\n]{0,120})",
        _normalize(body),
        re.I,
    )
    if not match:
        return None, None
    fragment = body[match.start(1):match.end(1)]
    amounts = re.findall(r"([0-9][0-9 .\xa0]*)\s*(?:tis\.)?\s*Kc", _normalize(fragment), re.I)
    if len(amounts) < 2:
        # fallback to two numeric money values before next known label
        raw = re.findall(r"([0-9][0-9 .\xa0]*)", fragment)
        amounts = raw[:2]
    parsed: list[int] = []
    for amount in amounts[:2]:
        digits = re.sub(r"[^0-9]", "", amount)
        if digits:
            value = int(digits)
            # "50 tis." appears normalized without a reliable currency magnitude parser.
            if "tis" in _normalize(fragment) and value < 10000:
                value *= 1000
            parsed.append(value * 100)
    return (
        parsed[0] if len(parsed) >= 1 else None,
        parsed[1] if len(parsed) >= 2 else None,
    )


def _cofinancing(body: str) -> str | None:
    value = _labeled_paragraph(
        body,
        "Minimální spoluúčast žadatele",
        stop_labels=("Kontaktní osoby", "Kontaktní osoba", "Další podmínky"),
    )
    return value[:1200] if value else None


def _applicants(body: str) -> str | None:
    value = _labeled_paragraph(
        body,
        "Oprávněný žadatel",
        stop_labels=(
            "Minimální a maximální výše dotace",
            "Minimální spoluúčast žadatele",
            "Kontaktní osoby",
            "Kontaktní osoba",
        ),
    )
    return value[:8000] if value else None


def _purpose(body: str) -> str | None:
    value = _labeled_paragraph(
        body,
        "Cíl programu",
        stop_labels=("Popis programu", "Oprávněný žadatel"),
    )
    if value:
        return value[:8000]
    value = _labeled_paragraph(
        body,
        "Program je zaměřen",
        stop_labels=("Oprávněný žadatel",),
    )
    return value[:8000] if value else None


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


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS or url in seen:
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        parent = anchor.find_parent(["li", "p", "div"])
        context = _clean(parent.get_text(" ", strip=True)) if parent else label
        mime = _mime_hint(url)
        if mime is None and "stahnout" not in _normalize(label):
            continue
        if _DETAIL_RE.match(parsed.path.rstrip("/") or "/"):
            continue
        seen.add(url)
        folded = _normalize(context)
        role = (
            "CALL_DOCUMENT"
            if "vyzva" in folded or "pravid" in folded or "program" in folded
            else "APPLICATION_FORM"
            if "zadost" in folded or "formular" in folded
            else "ANNEX"
        )
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=context[:500] or url,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


def _application_url(soup: BeautifulSoup, base_url: str) -> str | None:
    for anchor in soup.find_all("a", href=True):
        label = _normalize(_clean(anchor.get_text(" ", strip=True)))
        if "podat zadost" in label:
            return urljoin(base_url, anchor["href"])
    return None


class PardubickyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="PAK",
        name="Pardubický kraj — Dotační portál",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://dotace.pardubickykraj.cz/",
        retrieval_modes=[
            RetrievalMode.HTML,
            RetrievalMode.PDF,
            RetrievalMode.DOCX,
            RetrievalMode.XLSX,
        ],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=180,
        max_concurrency=2,
        requests_per_second=1.0,
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
                and "dotacni programy" in folded
                and "prejit na detail" in folded
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Pardubický grant index: HTTP {response.status_code}"
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
            raise RuntimeError(f"Pardubický grant index returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=INDEX_URL,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        items: list[DiscoveryItem] = []

        for url, title, card_text in _detail_links(soup):
            uuid_match = _DETAIL_RE.match(urlsplit(url).path.rstrip("/") or "/")
            if not uuid_match:
                continue
            grant_uuid = uuid_match.group(1).lower()
            opens, closes = _card_dates(card_text)
            items.append(
                DiscoveryItem(
                    external_id=f"PAK-{grant_uuid}",
                    detail_url=url,
                    title_hint=title,
                    native_status_hint=_status(ctx.now, opens, closes, card_text),
                    metadata={
                        "grant_uuid": grant_uuid,
                        "submission_open_at": opens.isoformat() if opens else None,
                        "submission_close_at": closes.isoformat() if closes else None,
                        "discovery_snapshot_id": snapshot_id,
                        "discovery_card_text": card_text[:3000],
                        "discovery_method": "official-public-grants-index",
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
            raise RuntimeError(f"Pardubický grant detail returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        body = _body_text(soup)
        heading = soup.find(["h1", "h2", "h3", "h4", "h5"])
        title = _clean(heading.get_text(" ", strip=True)) if heading else (item.title_hint or item.external_id)

        opens, closes = _application_window(body)
        if opens is None:
            raw = item.metadata.get("submission_open_at")
            opens = datetime.fromisoformat(raw) if raw else None
        if closes is None:
            raw = item.metadata.get("submission_close_at")
            closes = datetime.fromisoformat(raw) if raw else None

        grant_min, grant_max = _grant_range(body)
        cofinance_text = _cofinancing(body)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes, body),
                raw_fields={
                    "sourceGrantUuid": item.metadata.get("grant_uuid"),
                    "supportedActivitiesText": _purpose(body),
                    "eligibleApplicantsText": _applicants(body),
                    "grantAmountMinMinor": grant_min,
                    "grantAmountMaxMinor": grant_max,
                    "ownContributionText": cofinance_text,
                    "ownContributionMinBps": _percent_bps(cofinance_text),
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "applicationUrl": _application_url(soup, str(item.detail_url)),
                    "regionCode": "CZ053",
                    "regionName": "Pardubický kraj",
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
            raise RuntimeError(f"Pardubický artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("Pardubický adapter requires ctx.snapshots")
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
