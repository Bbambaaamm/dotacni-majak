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

ROOT_URL = "https://dotace.kraj-lbc.cz/"
_ALLOWED_HOSTS = {"dotace.kraj-lbc.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")

_EXCLUDED_ROOT_PATHS = {
    "",
    "/",
}
_EXCLUDED_CATEGORY_LABELS = {
    "dotace",
    "aktualne",
    "zastupitelstvo",
    "krajsky urad",
    "magazin",
    "english",
    "prihlasit se",
    "zastity bez financni podpory",
}


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _date(value: str | None, *, closing: bool = False) -> datetime | None:
    if not value:
        return None
    match = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b", value)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    local_time = time(23, 59, 59) if closing else time.min
    return datetime.combine(
        datetime(year, month, day).date(),
        local_time,
        tzinfo=_LOCAL_TZ,
    ).astimezone(timezone.utc)


def _money_minor(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(
        r"(?:alokovan(?:y|ý)|alokace|financnich prostredku).*?([0-9][0-9 .\xa0]{2,})\s*Kc",
        _normalize(value),
        re.I | re.S,
    )
    if not match:
        return None
    digits = re.sub(r"[^0-9]", "", match.group(1))
    return int(digits) * 100 if digits else None


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes and current > closes:
        return "CLOSED"
    if opens or closes:
        return "OPEN"
    return "UNKNOWN"


def _category_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True))
        folded = _normalize(label)
        if not label or folded in _EXCLUDED_CATEGORY_LABELS:
            continue
        url = urljoin(ROOT_URL, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        path = parsed.path.rstrip("/")
        if path in _EXCLUDED_ROOT_PATHS:
            continue
        if path.startswith("/getFile") or path.count("/") != 1:
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append((url, label))
    return result


def _detail_links(soup: BeautifulSoup, category_url: str) -> list[tuple[str, str]]:
    category_path = urlsplit(category_url).path.rstrip("/")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(category_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        path = parsed.path.rstrip("/")
        if not path.startswith(category_path + "/"):
            continue
        if not re.search(r"-d\d+\.htm$", path, re.I):
            continue
        if url in seen:
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        if not label:
            continue
        seen.add(url)
        result.append((url, label))
    return result


def _external_id(url: str) -> str:
    match = re.search(r"-d(\d+)\.htm$", urlsplit(url).path, re.I)
    if match:
        return f"LBK-{match.group(1)}"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"LBK-{digest}"


def _body_text(soup: BeautifulSoup) -> str:
    main = soup.find("main") or soup
    return _clean(main.get_text(" ", strip=True))


def _label_date(body: str, label: str, *, closing: bool = False) -> datetime | None:
    folded = _normalize(body)
    wanted = _normalize(label)
    pos = folded.find(wanted)
    if pos < 0:
        return None
    return _date(body[pos:pos + 120], closing=closing)


def _summary(soup: BeautifulSoup) -> str | None:
    current_heading = None
    for heading in soup.find_all(["h2", "h3"]):
        if _normalize(_clean(heading.get_text(" ", strip=True))) == "aktualne":
            current_heading = heading
            break
    if current_heading is None:
        return None
    chunks: list[str] = []
    for node in current_heading.next_siblings:
        if isinstance(node, Tag) and node.name in {"h2", "h3"}:
            break
        if isinstance(node, Tag):
            text = _clean(node.get_text(" ", strip=True))
        else:
            text = _clean(str(node))
        if text:
            chunks.append(text)
    value = _clean(" ".join(chunks))
    return value[:8000] or None


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        if "/getFile/" not in parsed.path and "/getFile" not in parsed.path:
            continue
        if url in seen:
            continue
        seen.add(url)
        label = _clean(anchor.get_text(" ", strip=True))
        folded = _normalize(label)
        role = (
            "CALL_DOCUMENT"
            if "vyhlas" in folded or "pravid" in folded or "zasad" in folded
            else "APPLICATION_FORM"
            if "zadost" in folded or "formular" in folded
            else "ANNEX"
        )
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=label[:500] or url,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


class LibereckyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="LBK",
        name="Liberecký kraj — Dotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url=ROOT_URL,
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
            response = await ctx.http.get(ROOT_URL)
            folded = _normalize(response.text)
            healthy = (
                response.status_code == 200
                and "dotacemi krok za krokem" in folded
                and "jednotlive dotacni programy" in folded
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Liberecký grants root: HTTP {response.status_code}"
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
        root_response = await ctx.http.get(ROOT_URL)
        if root_response.status_code >= 400:
            raise RuntimeError(f"Liberecký grants root returned HTTP {root_response.status_code}")

        root_snapshot_id = self._snapshot(
            ctx,
            source_url=ROOT_URL,
            content=root_response.content,
            mime_type=root_response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=root_response.headers,
        )
        root_soup = BeautifulSoup(root_response.text, "html.parser")

        items: dict[str, DiscoveryItem] = {}
        for category_url, category_name in _category_links(root_soup):
            response = await ctx.http.get(category_url)
            if response.status_code >= 400:
                continue
            category_snapshot_id = self._snapshot(
                ctx,
                source_url=category_url,
                content=response.content,
                mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
                headers=response.headers,
            )
            soup = BeautifulSoup(response.text, "html.parser")
            for detail_url, title in _detail_links(soup, category_url):
                ext = _external_id(detail_url)
                items[ext] = DiscoveryItem(
                    external_id=ext,
                    detail_url=detail_url,
                    title_hint=title,
                    metadata={
                        "category": category_name,
                        "root_snapshot_id": root_snapshot_id,
                        "category_snapshot_id": category_snapshot_id,
                        "discovery_method": "official-category-pages",
                    },
                )

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
            raise RuntimeError(f"Liberecký grant detail returned HTTP {response.status_code}")

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
        body = _body_text(soup)

        published = _label_date(body, "Vyhlášení:")
        opens = _label_date(body, "Zahájení:")
        closes = _label_date(body, "Ukončení:", closing=True)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                published_at=published,
                raw_fields={
                    "category": item.metadata.get("category"),
                    "summaryText": _summary(soup),
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "totalAllocationMinor": _money_minor(body),
                    "regionCode": "CZ051",
                    "regionName": "Liberecký kraj",
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
            raise RuntimeError(f"Liberecký artifact returned HTTP {response.status_code}")

        mime = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
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
            raise RuntimeError("Liberecký adapter requires ctx.snapshots")
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
