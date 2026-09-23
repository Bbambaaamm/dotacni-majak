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

ROOT_URL = "https://www.kr-ustecky.cz/dotace"
INDEX_URLS = (
    "https://www.kr-ustecky.cz/oblast-informatiky-a-organizacnich-veci",
    "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje",
    "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje-1",
    "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje-2",
    "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje-3",
    "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje-4",
    "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje-5",
    "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje-6",
)
_ALLOWED_HOSTS = {"www.kr-ustecky.cz", "kr-ustecky.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_MAX_PAGES_PER_INDEX = 5

_NAV_LABELS = {
    "na zacatek", "predchozi", "nasledujici", "na konec",
    "kontakt", "mapa stranek", "prihlasit", "o webu",
}
_EXCLUDED_PATH_PREFIXES = (
    "/programove-dotace-usteckeho-kraje",
    "/oblast-",
    "/dotace",
    "/nabidka-temat",
    "/uredni-deska",
    "/kontakty",
)


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _external_id(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    slug = PurePosixPath(path).name
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize(slug)).strip("-")
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    return f"ULK-{normalized[:64]}-{digest}"


def _parse_date(value: str | None, *, closing: bool = False) -> datetime | None:
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
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) * 100 if digits else None


def _section_value(soup: BeautifulSoup, label: str) -> str | None:
    wanted = _normalize(label)
    for heading in soup.find_all(["h2", "h3"]):
        if _normalize(_clean(heading.get_text(" ", strip=True))) != wanted:
            continue
        chunks: list[str] = []
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h2", "h3"}:
                break
            if isinstance(sibling, Tag):
                text = _clean(sibling.get_text(" ", strip=True))
            else:
                text = _clean(str(sibling))
            if text:
                chunks.append(text)
        value = _clean(" ".join(chunks))
        return value or None
    return None


def _explicit_status(value: str | None) -> str | None:
    if not value:
        return None
    folded = _normalize(value)
    if "ukoncen" in folded:
        return "CLOSED"
    if "pozastaven" in folded:
        return "PAUSED"
    if "priprav" in folded or "pred vyhlasenim" in folded:
        return "PLANNED"
    if "probih" in folded or "prijem zadosti" in folded:
        return "OPEN"
    return None


def _status(
    now: datetime,
    *,
    explicit: str | None,
    opens: datetime | None,
    closes: datetime | None,
) -> str:
    if explicit in {"PAUSED", "CANCELLED"}:
        return explicit
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes and current > closes:
        return "CLOSED"
    if explicit:
        return explicit
    if opens or closes:
        return "OPEN"
    return "UNKNOWN"


def _article_links(soup: BeautifulSoup, page_url: str) -> tuple[list[tuple[str, str]], list[str]]:
    article_links: list[tuple[str, str]] = []
    pagination: list[str] = []

    section = None
    for heading in soup.find_all("h2"):
        label = _normalize(_clean(heading.get_text(" ", strip=True)))
        if label in {"clanky", "dlazdice"}:
            section = heading
            break
    if section is None:
        return article_links, pagination

    for element in section.find_all_next():
        if element is not section and isinstance(element, Tag) and element.name == "h2":
            break
        if not isinstance(element, Tag) or element.name != "a" or not element.get("href"):
            continue

        label = _clean(element.get_text(" ", strip=True))
        folded = _normalize(label)
        url = urljoin(page_url, element["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue

        if parsed.path.rstrip("/") == urlsplit(page_url).path.rstrip("/") and parsed.query:
            if folded.isdigit() or folded in _NAV_LABELS:
                pagination.append(url)
            continue

        path = parsed.path.rstrip("/")
        if not label or folded in _NAV_LABELS:
            continue
        if any(path.startswith(prefix) for prefix in _EXCLUDED_PATH_PREFIXES):
            continue
        if path.count("/") != 1:
            continue
        article_links.append((url, label))

    return article_links, pagination


def _material_links(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    heading = None
    for candidate in soup.find_all(["h2", "h3"]):
        if _normalize(_clean(candidate.get_text(" ", strip=True))) == "materialy":
            heading = candidate
            break
    if heading is None:
        return []

    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for element in heading.find_all_next():
        if element is not heading and isinstance(element, Tag) and element.name in {"h2", "h3"}:
            break
        if not isinstance(element, Tag) or element.name != "a" or not element.get("href"):
            continue
        url = urljoin(base_url, element["href"])
        if (urlsplit(url).hostname or "").lower() not in _ALLOWED_HOSTS or url in seen:
            continue
        seen.add(url)
        label = _clean(element.get_text(" ", strip=True))
        path = urlsplit(url).path.casefold()
        mime = None
        if path.endswith(".pdf"):
            mime = "application/pdf"
        elif path.endswith((".doc", ".docx")):
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif path.endswith((".xls", ".xlsx", ".xlsm")):
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif path.endswith(".zip"):
            mime = "application/zip"
        folded = _normalize(label)
        role = (
            "CALL_DOCUMENT"
            if "dotacni program" in folded or "pravid" in folded
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
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


def _application_url(soup: BeautifulSoup, base_url: str) -> str | None:
    for heading in soup.find_all(["h2", "h3"]):
        if _normalize(_clean(heading.get_text(" ", strip=True))) != "odkazy":
            continue
        for element in heading.find_all_next():
            if element is not heading and isinstance(element, Tag) and element.name in {"h2", "h3"}:
                break
            if not isinstance(element, Tag) or element.name != "a" or not element.get("href"):
                continue
            label = _normalize(_clean(element.get_text(" ", strip=True)))
            if "elektronicka zadost" in label:
                return urljoin(base_url, element["href"])
    return None


class UsteckyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="ULK",
        name="Ústecký kraj — programové dotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.kr-ustecky.cz/",
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
            health_url = "https://www.kr-ustecky.cz/programove-dotace-usteckeho-kraje-2"
            response = await ctx.http.get(health_url)
            folded = _normalize(response.text)
            healthy = (
                response.status_code == 200
                and "programove dotace usteckeho kraje" in folded
                and "clanky" in folded
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Ústecký programme index: HTTP {response.status_code}"
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
        queue = list(INDEX_URLS)
        visited: set[str] = set()
        items: dict[str, DiscoveryItem] = {}
        page_counts: dict[str, int] = {}

        while queue:
            page_url = queue.pop(0)
            if page_url in visited:
                continue
            visited.add(page_url)

            base_path = urlsplit(page_url).path.rstrip("/")
            page_counts[base_path] = page_counts.get(base_path, 0) + 1
            if page_counts[base_path] > _MAX_PAGES_PER_INDEX:
                continue

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
            links, pagination = _article_links(soup, page_url)

            for url, title in links:
                ext = _external_id(url)
                items[ext] = DiscoveryItem(
                    external_id=ext,
                    detail_url=url,
                    title_hint=title,
                    metadata={
                        "discovery_snapshot_id": snapshot_id,
                        "discovery_page": page_url,
                        "discovery_method": "official-area-article-list",
                    },
                )

            for url in pagination:
                if url not in visited and url not in queue:
                    queue.append(url)

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
            raise RuntimeError(f"Ústecký grant detail returned HTTP {response.status_code}")

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

        source_code = _section_value(soup, "Kód výzvy")
        area = _section_value(soup, "Oblast dotace")
        allocation_text = _section_value(soup, "Finanční alokace")
        opens = _parse_date(_section_value(soup, "Datum zahájení sběru žádostí"))
        closes = _parse_date(_section_value(soup, "Datum ukončení sběru žádosti"), closing=True)
        if closes is None:
            closes = _parse_date(_section_value(soup, "Datum ukončení sběru žádostí"), closing=True)
        explicit = _explicit_status(_section_value(soup, "Stav dotačního programu"))
        applicant_text = _section_value(soup, "Typ žadatele")
        planned_announcement = _parse_date(_section_value(soup, "Předpokládaný termín vyhlášení výzvy"))
        planned_collection = _parse_date(_section_value(soup, "Předpokládaný termín sběru žádostí"))

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, explicit=explicit, opens=opens, closes=closes),
                raw_fields={
                    "sourceCallCode": source_code,
                    "programme": "Ústecký kraj — programové dotace",
                    "grantAreaText": area,
                    "eligibleApplicantsText": applicant_text,
                    "totalAllocationMinor": _money_minor(allocation_text),
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "plannedAnnouncementAt": planned_announcement.isoformat() if planned_announcement else None,
                    "plannedCollectionAt": planned_collection.isoformat() if planned_collection else None,
                    "applicationUrl": _application_url(soup, str(item.detail_url)),
                    "regionCode": "CZ042",
                    "regionName": "Ústecký kraj",
                    "providerStatusText": _section_value(soup, "Stav dotačního programu"),
                    "discoveryMethod": item.metadata.get("discovery_method"),
                },
                artifacts=_material_links(soup, str(item.detail_url)),
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
            raise RuntimeError(f"Ústecký grant artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("Ústecký adapter requires ctx.snapshots")
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
