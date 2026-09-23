from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, time, timezone
from email.utils import parsedate_to_datetime
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


RSS_URL = (
    "https://eud.praha.eu/pub/rss/6000004/4/"
    "?cislo_jednaci=&datum_do=&datum_od=&kategorie_id=24&nazev="
    "&pocet=25&pozice=0&rss=True&text=&trideni=&vizual=mhmp_res"
)

_ALLOWED_HOSTS = {
    "eud.praha.eu",
    "eud-vis.praha.eu",
    "praha.eu",
    "www.praha.eu",
    "granty.praha.eu",
}
_LOCAL_TZ = ZoneInfo("Europe/Prague")


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _safe_rss_root(content: bytes) -> ET.Element:
    probe = content.upper()
    if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
        raise ValueError("RSS DTD/entity declarations are forbidden")
    return ET.fromstring(content)


def _text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return _clean(child.text or "") if child is not None and child.text else ""


def _html_text(value: str) -> str:
    return _clean(BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True))


def _notice_number(text: str) -> str | None:
    match = re.search(r"\bMHMP\s+(\d{4,9})/(20\d{2})\b", text, re.I)
    if not match:
        return None
    return f"MHMP {match.group(1)}/{match.group(2)}"


def _external_id(*, title: str, description: str, guid: str, link: str) -> str:
    notice = _notice_number(description) or _notice_number(title)
    if notice:
        return "PRAHA-" + re.sub(r"[^0-9/]+", "", notice).replace("/", "-")
    if guid:
        digest = hashlib.sha256(guid.encode("utf-8")).hexdigest()[:24]
        return f"PRAHA-{digest}"
    digest = hashlib.sha256(link.encode("utf-8")).hexdigest()[:24]
    return f"PRAHA-{digest}"


def _is_probable_call(title: str) -> bool:
    folded = _normalize(title)
    blocked = (
        "odpoved",
        "zadost o informaci",
        "informace podle zakona",
        "projekt ",
        "dotacni zadosti",
        "vyuctovani",
        "schvaleni ",
        "vysledk",
        "rozhodnuti",
    )
    if any(token in folded for token in blocked):
        return False
    positive = (
        "program ",
        "programu ",
        "vyhlaseni ",
        "dotacni rizeni",
        "grant",
        "vyzva",
        "podpory ",
    )
    return any(token in folded for token in positive)


def _published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_cz_date(value: str, *, end_of_day: bool = False) -> datetime | None:
    match = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b", value)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    local = datetime.combine(
        datetime(year, month, day).date(),
        time(23, 59, 59) if end_of_day else time.min,
        tzinfo=_LOCAL_TZ,
    )
    return local.astimezone(timezone.utc)


def _explicit_application_window(body: str) -> tuple[datetime | None, datetime | None]:
    folded = _normalize(body)
    patterns = (
        r"(?:zadosti|zadost).*?(?:podavat|podani|prijem).*?"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2}).{0,120}?"
        r"(?:do|az).*?(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
        r"(?:prijem zadosti|lhuta pro podani zadosti).*?"
        r"(?:od\s*)?(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2}).{0,120}?"
        r"(?:do|az).*?(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, folded, re.I | re.S)
        if match:
            return (
                _parse_cz_date(match.group(1)),
                _parse_cz_date(match.group(2), end_of_day=True),
            )
    single = re.search(
        r"(?:termin|lhuta).*?podani.*?(?:do\s*)?"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
        folded,
        re.I | re.S,
    )
    if single:
        return None, _parse_cz_date(single.group(1), end_of_day=True)
    return None, None


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes:
        return "CLOSED" if current > closes else "OPEN"
    return "UNKNOWN"


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.casefold()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.endswith((".xlsx", ".xlsm")):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if path.endswith(".zip"):
        return "application/zip"
    return None


def _artifact_role(title: str) -> str:
    folded = _normalize(title)
    if "vyzva" in folded or "program" in folded:
        return "CALL_DOCUMENT"
    if "pravid" in folded or "metodik" in folded:
        return "GUIDELINES"
    if "zadost" in folded or "formular" in folded:
        return "APPLICATION_FORM"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        host = (urlsplit(url).hostname or "").lower()
        if host not in _ALLOWED_HOSTS or url in seen:
            continue
        mime = _mime_hint(url)
        if mime is None:
            continue
        seen.add(url)
        title = _clean(anchor.get_text(" ", strip=True)) or PurePosixPath(urlsplit(url).path).name
        role = _artifact_role(title)
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=title,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


class PrahaAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="PRAHA",
        name="Hlavní město Praha — granty a dotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://eud.praha.eu/",
        retrieval_modes=[RetrievalMode.RSS, RetrievalMode.HTML, RetrievalMode.PDF, RetrievalMode.DOCX, RetrievalMode.XLSX],
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
            response = await ctx.http.get(RSS_URL)
            root = _safe_rss_root(response.content)
            items = root.findall(".//item")
            healthy = response.status_code == 200 and bool(items)
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Prague grants RSS: HTTP {response.status_code}, items={len(items)}"
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
        response = await ctx.http.get(RSS_URL)
        if response.status_code >= 400:
            raise RuntimeError(f"Prague RSS returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=RSS_URL,
            content=response.content,
            mime_type=response.headers.get("content-type", "application/rss+xml").split(";", 1)[0],
            headers=response.headers,
        )

        root = _safe_rss_root(response.content)
        items: list[DiscoveryItem] = []
        seen: set[str] = set()
        for entry in root.findall(".//item"):
            title = _text(entry, "title")
            link = _text(entry, "link")
            description = _html_text(_text(entry, "description"))
            guid = _text(entry, "guid")
            pub_date = _published(_text(entry, "pubDate"))
            if not title or not link or not _is_probable_call(title):
                continue
            host = (urlsplit(link).hostname or "").lower()
            if host not in _ALLOWED_HOSTS:
                continue
            external_id = _external_id(
                title=title,
                description=description,
                guid=guid,
                link=link,
            )
            if external_id in seen:
                continue
            seen.add(external_id)
            items.append(
                DiscoveryItem(
                    external_id=external_id,
                    detail_url=link,
                    title_hint=title,
                    published_at_hint=pub_date,
                    metadata={
                        "notice_number": _notice_number(description),
                        "rss_description": description,
                        "discovery_snapshot_id": snapshot_id,
                        "discovery_method": "official-rss",
                    },
                )
            )

        return DiscoveryPage(
            items=sorted(items, key=lambda item: item.external_id),
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
            raise RuntimeError(f"Prague detail returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        heading = soup.find(["h1", "h2", "h3"])
        title = _clean(heading.get_text(" ", strip=True)) if heading else (item.title_hint or item.external_id)
        body = _clean(soup.get_text(" ", strip=True))
        opens, closes = _explicit_application_window(body)
        notice = _notice_number(body) or item.metadata.get("notice_number")

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                published_at=item.published_at_hint,
                raw_fields={
                    "programme": "Hlavní město Praha — dotační programy",
                    "noticeNumber": notice,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "regionCode": "CZ010",
                    "regionName": "Hlavní město Praha",
                    "discoveryMethod": item.metadata.get("discovery_method"),
                    "coverageNote": (
                        "Discovery uses the official Prague notice-board Granty RSS feed. "
                        "Notice-board display-until dates are NOT interpreted as application deadlines; "
                        "submission dates are populated only when explicitly stated in the detail."
                    ),
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
            raise RuntimeError(f"Prague artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("Prague adapter requires ctx.snapshots")
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
