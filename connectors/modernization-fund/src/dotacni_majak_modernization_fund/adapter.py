from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit
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


LISTING_URL = "https://sfzp.gov.cz/dotace-a-pujcky/modernizacni-fond/vyzvy/"
_ALLOWED_HOSTS = {
    "sfzp.gov.cz",
    "www.sfzp.gov.cz",
    "sfzp.cz",
    "www.sfzp.cz",
}
_DETAIL_PATH = "/dotace-a-pujcky/modernizacni-fond/vyzvy/detail-vyzvy/"
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_MONTHS = {
    "ledna": 1,
    "února": 2,
    "unora": 2,
    "března": 3,
    "brezna": 3,
    "dubna": 4,
    "května": 5,
    "kvetna": 5,
    "června": 6,
    "cervna": 6,
    "července": 7,
    "cervence": 7,
    "srpna": 8,
    "září": 9,
    "zari": 9,
    "října": 10,
    "rijna": 10,
    "listopadu": 11,
    "prosince": 12,
}


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _call_id(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.path.rstrip("/") != _DETAIL_PATH.rstrip("/"):
        return None
    values = parse_qs(parsed.query).get("id")
    if not values or not values[0].isdigit():
        return None
    return f"MODF-{int(values[0])}"


def _numeric_date(value: str, *, end_of_day: bool = False) -> datetime | None:
    match = re.search(
        r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(20\d{2})(?!\d)",
        value,
    )
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    local_time = time.max if end_of_day else time.min
    return datetime.combine(
        datetime(year, month, day).date(),
        local_time,
        tzinfo=_LOCAL_TZ,
    ).astimezone(timezone.utc)


def _czech_datetime(value: str) -> datetime | None:
    match = re.search(
        r"(\d{1,2})\.\s*([A-Za-zÁ-ž]+)\s+(20\d{2})"
        r"(?:\s*,?\s*(\d{1,2}):(\d{2}))?",
        value,
        re.I,
    )
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2).casefold()
    month = _MONTHS.get(month_name)
    if month is None:
        return None
    year = int(match.group(3))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        tzinfo=_LOCAL_TZ,
    ).astimezone(timezone.utc)


def _submission_range(text: str) -> tuple[datetime | None, datetime | None]:
    match = re.search(
        r"Příjem\s+žádostí\s*:\s*"
        r"(\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*20\d{2})"
        r"\s*[-–]\s*"
        r"(\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*20\d{2})",
        text,
        re.I,
    )
    if not match:
        return None, None
    return (
        _numeric_date(match.group(1)),
        _numeric_date(match.group(2), end_of_day=True),
    )


def _explicit_term(text: str, label: str) -> datetime | None:
    pattern = re.compile(
        re.escape(label)
        + r"\s*:\s*"
        + r"(\d{1,2}\.\s*[A-Za-zÁ-ž]+\s+20\d{2}(?:\s*,?\s*\d{1,2}:\d{2}\s*(?:hod\.)?)?)",
        re.I,
    )
    match = pattern.search(text)
    return _czech_datetime(match.group(1)) if match else None


def _published_at(soup: BeautifulSoup) -> datetime | None:
    time_tag = soup.find("time")
    if time_tag is not None:
        candidate = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
        parsed = _numeric_date(str(candidate))
        if parsed:
            return parsed

    h1 = soup.find("h1")
    if h1 is not None:
        for element in h1.find_all_next(["p", "div", "span"], limit=10):
            parsed = _numeric_date(_clean(element.get_text(" ", strip=True)))
            if parsed:
                return parsed
    return None


def _section_text(soup: BeautifulSoup, heading_text: str) -> str | None:
    target = heading_text.casefold()
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        label = _clean(heading.get_text(" ", strip=True)).casefold()
        if label != target:
            continue
        parts: list[str] = []
        for element in heading.find_all_next():
            if element is not heading and element.name and re.fullmatch(r"h[1-6]", element.name):
                break
            if element.name not in {"p", "li"}:
                continue
            text = _clean(element.get_text(" ", strip=True))
            if text and text not in parts:
                parts.append(text)
        return "\n".join(parts) or None
    return None


def _support_rate(section: str | None) -> float | None:
    if not section:
        return None
    match = re.search(
        r"(?:maximálně|max\.)\s*([0-9]+(?:[,.][0-9]+)?)\s*%",
        section,
        re.I,
    )
    if not match:
        match = re.search(r"([0-9]+(?:[,.][0-9]+)?)\s*%", section)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _money_czk(text: str | None) -> int | None:
    if not text:
        return None
    normalized = text.replace("\xa0", " ")
    million = re.search(
        r"([0-9]+(?:[,.][0-9]+)?)\s*(?:mil\.?|milion(?:ů|u|y)?)\s*(?:Kč|korun)?",
        normalized,
        re.I,
    )
    if million:
        return int(round(float(million.group(1).replace(",", ".")) * 1_000_000))

    direct = re.search(r"([0-9][0-9\s]*)\s*Kč\b", normalized, re.I)
    if direct:
        return int(re.sub(r"\s+", "", direct.group(1)))
    return None


def _native_status(
    *,
    opens_at: datetime | None,
    closes_at: datetime | None,
    body_text: str,
    now: datetime,
) -> str:
    lowered = body_text.casefold()
    if "výzva byla zrušena" in lowered or "výzva je zrušena" in lowered:
        return "CANCELLED"
    if "příjem žádostí byl pozastaven" in lowered:
        return "PAUSED"

    current = now.astimezone(timezone.utc)
    if opens_at is not None and current < opens_at:
        return "PLANNED"
    if closes_at is not None and current > closes_at:
        return "CLOSED"
    if opens_at is not None or closes_at is not None:
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
    if path.endswith(".xls"):
        return "application/vnd.ms-excel"
    if path.endswith(".zip"):
        return "application/zip"
    return None


def _artifact_role(title: str) -> str:
    lowered = title.casefold()
    if lowered.startswith("výzva ") or "text výzvy" in lowered:
        return "CALL_DOCUMENT"
    if "pokyn" in lowered or "metodik" in lowered or "manuál" in lowered:
        return "GUIDELINES"
    if "žádost" in lowered or "formulář" in lowered:
        return "APPLICATION_FORM"
    if "faq" in lowered or "čast" in lowered and "dotaz" in lowered:
        return "FAQ"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    heading = None
    for candidate in soup.find_all(re.compile(r"^h[1-6]$")):
        if _clean(candidate.get_text(" ", strip=True)).casefold() == "dokumenty ke stažení":
            heading = candidate
            break
    if heading is None:
        return []

    seen: set[str] = set()
    artifacts: list[RemoteArtifactRef] = []
    for element in heading.find_all_next():
        if element is not heading and element.name and re.fullmatch(r"h[1-6]", element.name):
            break
        if element.name != "a" or not element.get("href"):
            continue

        url = urljoin(base_url, element["href"])
        parsed = urlsplit(url)
        if parsed.hostname not in _ALLOWED_HOSTS:
            continue
        mime = _mime_hint(url)
        if mime is None and "/files/documents/" not in parsed.path:
            continue
        if url in seen:
            continue
        seen.add(url)

        title = _clean(element.get_text(" ", strip=True))
        if not title or title.casefold() == "stáhnout":
            parent = element.parent
            if parent is not None:
                title = _clean(parent.get_text(" ", strip=True)).replace("stáhnout", "").strip()
        if not title:
            title = PurePosixPath(parsed.path).name

        role = _artifact_role(title)
        artifacts.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=title,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return artifacts


class ModernizationFundAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="MODF",
        name="Modernizační fond / SFŽP",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://sfzp.gov.cz/",
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
                and "výzvy modernizačního fondu" in body
                and "příjem žádostí" in body
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else (
                f"Unexpected Modernisation Fund listing: HTTP {response.status_code}"
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
                f"Modernisation Fund listing returned HTTP {response.status_code}"
            )

        snapshot_id = self._snapshot(
            ctx,
            source_url=LISTING_URL,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        items: dict[str, DiscoveryItem] = {}
        for anchor in soup.find_all("a", href=True):
            url = urljoin(LISTING_URL, anchor["href"])
            external_id = _call_id(url)
            if external_id is None:
                continue
            title = _clean(anchor.get_text(" ", strip=True))
            if not title:
                continue

            item = DiscoveryItem(
                external_id=external_id,
                detail_url=url,
                title_hint=title,
                metadata={
                    "listing_snapshot_id": snapshot_id,
                    "discovery_method": "SERVER_RENDERED_HTML",
                },
            )
            items[external_id] = item

        return DiscoveryPage(
            items=sorted(items.values(), key=lambda item: item.external_id),
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
                f"Modernisation Fund detail returned HTTP {response.status_code}"
            )

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        title = (
            _clean(h1.get_text(" ", strip=True))
            if h1 is not None
            else (item.title_hint or item.external_id)
        )
        body = _clean(soup.get_text(" ", strip=True))

        opens_at, closes_at = _submission_range(body)
        exact_open = _explicit_term(body, "Zahájení příjmu žádostí")
        exact_close = _explicit_term(body, "Ukončení příjmu žádostí")
        opens_at = exact_open or opens_at
        closes_at = exact_close or closes_at

        activities = _section_text(soup, "Na co můžete získat dotaci")
        applicants = _section_text(soup, "Kdo může žádat")
        contribution = _section_text(soup, "Výše příspěvku")
        total_funds = _section_text(soup, "Celkový objem prostředků")
        terms = _section_text(soup, "Termíny")
        application = _section_text(soup, "Jak podat žádost")

        record = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title=title,
            native_status=_native_status(
                opens_at=opens_at,
                closes_at=closes_at,
                body_text=body,
                now=ctx.now,
            ),
            published_at=_published_at(soup),
            raw_fields={
                "programme": "Modernizační fond",
                "supportedActivitiesText": activities,
                "eligibleApplicantsText": applicants,
                "supportRateMaxPercent": _support_rate(contribution),
                "allocationCzk": _money_czk(total_funds) or _money_czk(body),
                "submissionOpenAt": opens_at.isoformat() if opens_at else None,
                "submissionCloseAt": closes_at.isoformat() if closes_at else None,
                "termsText": terms,
                "applicationText": application,
                "discoveryMethod": item.metadata.get("discovery_method"),
                "coverageCaveat": (
                    "Server-rendered listing can expose only the initial result set; "
                    "live smoke/source health must detect load-more regressions."
                ),
            },
            artifacts=_artifacts(soup, str(item.detail_url)),
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
                f"Modernisation Fund artifact returned HTTP {response.status_code}"
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
            raise RuntimeError(
                "Modernisation Fund adapter requires ctx.snapshots"
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
