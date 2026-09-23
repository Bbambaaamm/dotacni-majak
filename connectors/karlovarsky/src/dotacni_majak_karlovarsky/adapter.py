from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timezone
from pathlib import PurePosixPath
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


INDEX_URL = "https://www.kr-karlovarsky.cz/dotace/dotacni-programy-karlovarskeho-kraje"
_ALLOWED_HOSTS = {"www.kr-karlovarsky.cz", "kr-karlovarsky.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_MAX_PAGES = 12

_EXCLUDED_DETAIL_PREFIXES = (
    "/dotace/dotacni-programy-karlovarskeho-kraje",
)
_EXCLUDED_PATHS = {
    "/dotace",
    "/dotace/dulezite-informace-pro-zadatele-o-dotace-z-rozpoctu-karlovarskeho-kraje",
    "/dotace/postup-pro-podani-elektronicke-zadosti",
    "/dotace/caste-dotazy",
    "/dotace/informace-pro-zadatele",
}


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _is_program_detail(url: str) -> bool:
    parsed = urlsplit(url)
    if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
        return False
    path = parsed.path.rstrip("/")
    if path in _EXCLUDED_PATHS:
        return False
    if any(path.startswith(prefix) for prefix in _EXCLUDED_DETAIL_PREFIXES):
        return False
    return path.startswith("/dotace/") and path.count("/") == 2


def _external_id(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    slug = PurePosixPath(path).name
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize(slug)).strip("-")
    return f"KVK-{normalized[:70]}-{digest}"


def _date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
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


def _local_datetime(
    date_value: str,
    *,
    hour: str | None = None,
    minute: str | None = None,
    end_of_day_if_no_time: bool = False,
) -> datetime | None:
    match = re.search(
        r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b",
        date_value,
    )
    if not match:
        return None
    day, month, year = map(int, match.groups())
    if hour is None or minute is None:
        local_time = time(23, 59, 59) if end_of_day_if_no_time else time.min
        local = datetime.combine(
            datetime(year, month, day).date(),
            local_time,
            tzinfo=_LOCAL_TZ,
        )
    else:
        local = datetime(
            year,
            month,
            day,
            int(hour),
            int(minute),
            tzinfo=_LOCAL_TZ,
        )
    return local.astimezone(timezone.utc)


def _application_window(body: str) -> tuple[datetime | None, datetime | None]:
    """Extract only explicitly labelled application dates.

    Prefer the detailed sentence with exact local times. If that sentence is
    absent, fall back to the provider's separate "Příjem elektronických
    žádostí od/do" date labels. We deliberately do not search for generic
    words "od" / "do", which occur frequently in unrelated page content.
    """

    folded = _normalize(body)

    detailed = re.search(
        r"lhuta\s+pro\s+podavani\s+elektronickych\s+zadosti"
        r".{0,180}?\bod\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"(?:\s*,?\s*(\d{1,2})[.:](\d{2}))?"
        r"(?:\s*hodin)?"
        r".{0,120}?\bdo\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"(?:\s*,?\s*(\d{1,2})[.:](\d{2}))?",
        folded,
        re.I | re.S,
    )
    if detailed:
        opens = _local_datetime(
            detailed.group(1),
            hour=detailed.group(2),
            minute=detailed.group(3),
        )
        closes = _local_datetime(
            detailed.group(4),
            hour=detailed.group(5),
            minute=detailed.group(6),
            end_of_day_if_no_time=True,
        )
        return opens, closes

    open_match = re.search(
        r"prijem\s+elektronickych\s+zadosti\s+od\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"(?:\s*,?\s*(\d{1,2})[.:](\d{2}))?",
        folded,
        re.I,
    )
    close_match = re.search(
        r"prijem\s+elektronickych\s+zadosti\s+do\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})"
        r"(?:\s*,?\s*(\d{1,2})[.:](\d{2}))?",
        folded,
        re.I,
    )

    opens = (
        _local_datetime(
            open_match.group(1),
            hour=open_match.group(2),
            minute=open_match.group(3),
        )
        if open_match
        else None
    )
    closes = (
        _local_datetime(
            close_match.group(1),
            hour=close_match.group(2),
            minute=close_match.group(3),
            end_of_day_if_no_time=True,
        )
        if close_match
        else None
    )
    return opens, closes


def _status_from_text(body: str) -> str:
    folded = _normalize(body)
    if "prijem zadosti se pripravuje" in folded:
        return "PLANNED"
    if "prijem zadosti pozastaven" in folded:
        return "PAUSED"
    if "prijem zadosti ukoncen" in folded:
        return "CLOSED"
    if re.search(r"\bprijem zadosti\b", folded):
        return "OPEN"
    return "UNKNOWN"


def _field(body: str, label: str) -> str | None:
    folded = _normalize(body)
    normalized_label = _normalize(label)
    pos = folded.find(normalized_label)
    if pos < 0:
        return None
    raw = body[pos + len(label):]
    match = re.match(r"\s*:?\s*([^\n\r]{1,300})", raw)
    return _clean(match.group(1)) if match else None


def _labeled_text(soup: BeautifulSoup, label: str) -> str | None:
    wanted = _normalize(label)
    for node in soup.find_all(["dt", "th", "strong", "div", "span", "p"]):
        text = _clean(node.get_text(" ", strip=True))
        folded = _normalize(text)
        if folded == wanted or folded.startswith(wanted + " "):
            if folded.startswith(wanted + " ") and len(text) > len(label):
                return _clean(text[len(label):].lstrip(" :"))
            sibling = node.find_next_sibling()
            if sibling:
                value = _clean(sibling.get_text(" ", strip=True))
                if value:
                    return value
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
    if "pravid" in folded or "program " in folded or "vyhlas" in folded:
        return "CALL_DOCUMENT"
    if "priruck" in folded or "metodik" in folded:
        return "GUIDELINES"
    if "zadost" in folded or "formular" in folded:
        return "APPLICATION_FORM"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if (urlsplit(url).hostname or "").lower() not in _ALLOWED_HOSTS or url in seen:
            continue
        mime = _mime_hint(url)
        if mime is None:
            continue
        seen.add(url)
        parent = anchor.find_parent(["li", "p", "div"])
        context = _clean(parent.get_text(" ", strip=True)) if parent else _clean(anchor.get_text(" ", strip=True))
        role = _role(context)
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=(context or PurePosixPath(urlsplit(url).path).name)[:500],
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


class KarlovarskyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="KVK",
        name="Karlovarský kraj — dotační programy",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.kr-karlovarsky.cz/",
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
            response = await ctx.http.get(INDEX_URL)
            healthy = (
                response.status_code == 200
                and "dotacni programy karlovarskeho kraje" in _normalize(response.text)
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Karlovy Vary grant index: HTTP {response.status_code}"
        except Exception as exc:
            status = HealthStatus.UNAVAILABLE
            detail = f"{type(exc).__name__}: {exc}"
        elapsed = datetime.now(timezone.utc) - started
        return HealthReport(status=status, checked_at=ctx.now, latency_ms=max(0, int(elapsed.total_seconds()*1000)), detail=detail)

    async def discover(self, ctx: AdapterContext, checkpoint: SourceCheckpoint | None) -> DiscoveryPage:
        del checkpoint
        queue = [INDEX_URL]
        visited: set[str] = set()
        items: dict[str, DiscoveryItem] = {}

        while queue and len(visited) < _MAX_PAGES:
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

            for anchor in soup.find_all("a", href=True):
                url = urljoin(page_url, anchor["href"])
                parsed = urlsplit(url)
                if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
                    continue

                if _is_program_detail(url):
                    title = _clean(anchor.get_text(" ", strip=True))
                    if not title:
                        heading = anchor.find(["h2", "h3", "h4"])
                        title = _clean(heading.get_text(" ", strip=True)) if heading else ""
                    if not title:
                        continue
                    ext = _external_id(url)
                    items[ext] = DiscoveryItem(
                        external_id=ext,
                        detail_url=url,
                        title_hint=title,
                        metadata={
                            "discovery_snapshot_id": snapshot_id,
                            "discovery_page": page_url,
                            "discovery_method": "official-html-catalogue",
                        },
                    )
                    continue

                if parsed.path.rstrip("/") == urlsplit(INDEX_URL).path.rstrip("/"):
                    page = re.search(r"(?:^|&)page=(\d+)(?:&|$)", parsed.query)
                    if page and int(page.group(1)) < _MAX_PAGES and url not in visited and url not in queue:
                        queue.append(url)

        values = sorted(items.values(), key=lambda x: x.external_id)
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
            raise RuntimeError(f"Karlovy Vary detail returned HTTP {response.status_code}")

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
        body = _clean(soup.get_text(" ", strip=True))
        folded = _normalize(body)

        opens, closes = _application_window(body)

        area = _labeled_text(soup, "Oblast")
        contact = _labeled_text(soup, "Kontaktní osoba")
        explicit_status = _status_from_text(body)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=explicit_status,
                raw_fields={
                    "programme": "Karlovarský kraj — dotační programy",
                    "area": area,
                    "contactPerson": contact,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "regionCode": "CZ041",
                    "regionName": "Karlovarský kraj",
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
            raise RuntimeError(f"Karlovy Vary artifact returned HTTP {response.status_code}")

        mime = response.headers.get("content-type", artifact.mime_hint or "application/octet-stream").split(";", 1)[0]
        snapshot_id = self._snapshot(ctx, source_url=str(artifact.url), content=response.content, mime_type=mime, headers=response.headers)
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
            raise RuntimeError("Karlovarský adapter requires ctx.snapshots")
        snapshot = ctx.snapshots.put(
            source_code=self.descriptor.code,
            source_url=source_url,
            content=content,
            mime_type=mime_type,
            retrieved_at=ctx.now,
            validators={"etag": headers.get("etag") or "", "last_modified": headers.get("last-modified") or ""},
        )
        return snapshot.snapshot_id
