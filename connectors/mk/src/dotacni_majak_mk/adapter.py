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


CENTRAL_INDEX = "https://www.mk.gov.cz/granty-a-dotace-cs-1234"
_ALLOWED_HOSTS = {"mk.gov.cz", "www.mk.gov.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_MAX_INDEX_PAGES = 8

_CZ_MONTHS = {
    "ledna": 1, "února": 2, "unora": 2, "března": 3, "brezna": 3,
    "dubna": 4, "května": 5, "kvetna": 5, "června": 6, "cervna": 6,
    "července": 7, "cervence": 7, "srpna": 8, "září": 9, "zari": 9,
    "října": 10, "rijna": 10, "listopadu": 11, "prosince": 12,
}


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    text = _clean(value)
    numeric = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b", text)
    if numeric:
        year, month, day = int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1))
    else:
        named = re.search(r"\b(\d{1,2})\.\s*([A-Za-zÁ-ž]+)\s+(20\d{2})\b", text, re.I)
        if not named:
            return None
        month = _CZ_MONTHS.get(named.group(2).casefold())
        if month is None:
            month = _CZ_MONTHS.get(_normalize(named.group(2)))
        if month is None:
            return None
        day, year = int(named.group(1)), int(named.group(3))

    local = datetime.combine(
        datetime(year, month, day).date(),
        time(23, 59, 59) if end_of_day else time.min,
        tzinfo=_LOCAL_TZ,
    )
    return local.astimezone(timezone.utc)


def _deadline(body: str) -> datetime | None:
    # Prefer narrow, label-like formulations. Avoid a broad greedy pattern:
    # MK detail pages often contain several publication/programme dates before
    # the actual application deadline.
    patterns = (
        r"termín(?:em)?\s+podání(?:\s+žádost(?:i|í))?\s*(?:je|:)?\s*"
        r"(?:stanoven\s+)?(?:do\s+)?"
        r"(\d{1,2}\.\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2})",
        r"(?:příjem|prijem)\s+žádostí(?:[^.]{0,80})?\s+do\s+"
        r"(\d{1,2}\.\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2})",
        r"(?:uzávěrka|uzaverka|termín uzávěrky|termin uzaverky)\s*:?\s*"
        r"(\d{1,2}\.\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, body, re.I)
        if match:
            parsed = _date(match.group(1), end_of_day=True)
            if parsed:
                return parsed
    return None


def _status(now: datetime, closes: datetime | None) -> str:
    if closes is None:
        return "UNKNOWN"
    return "CLOSED" if now.astimezone(timezone.utc) > closes else "OPEN"


def _year_relevant(text: str, now: datetime) -> bool:
    years = {int(x) for x in re.findall(r"\b20\d{2}\b", text)}
    if not years:
        return True
    return bool(years & {now.year - 1, now.year, now.year + 1})


def _is_result_or_admin(title: str) -> bool:
    folded = _normalize(title)
    blocked = (
        "vysled", "vyuctov", "archiv", "komise", "navod", "zapis",
        "prehled vysled", "uspesnych projektu",
    )
    return any(token in folded for token in blocked)


def _is_call_link(title: str, url: str, now: datetime) -> bool:
    if not title or _is_result_or_admin(title) or not _year_relevant(title, now):
        return False
    folded = _normalize(title)
    path = _normalize(urlsplit(url).path)
    return (
        "vyzva c" in folded
        or "zadost o dotaci ze statniho rozpoctu" in folded
        or ("vyzva" in folded and "dotac" in folded)
        or "vyzva-c-" in path
    )


def _is_index_link(title: str, now: datetime) -> bool:
    if not title or _is_result_or_admin(title) or not _year_relevant(title, now):
        return False
    folded = _normalize(title)
    return (
        "vyhlaseni vyberovych dotacnich rizeni" in folded
        or "dotacni rizeni na rok" in folded
        or "granty a dotace" in folded
    )


def _external_id(title: str, url: str) -> str:
    code = re.search(r"výzva\s+č\.\s*(\d{3,5})", title, re.I)
    if code:
        return f"MK-{code.group(1)}"
    slug = PurePosixPath(urlsplit(url).path.rstrip("/")).name
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize(slug)).strip("-")
    return f"MK-{normalized[:100]}" if normalized else "MK-" + hashlib.sha256(url.encode()).hexdigest()[:20]


def _links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS or url in seen:
            continue
        title = _clean(anchor.get_text(" ", strip=True))
        if not title:
            continue
        seen.add(url)
        result.append((title, url))
    return result


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.casefold()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.endswith(".xlsx") or path.endswith(".xlsm"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if path.endswith(".zip"):
        return "application/zip"
    return None


def _artifact_role(title: str) -> str:
    folded = _normalize(title)
    if "priruck" in folded or "pravid" in folded or "metodik" in folded:
        return "GUIDELINES"
    if "zadost" in folded or "formular" in folded:
        return "APPLICATION_FORM"
    if "vyzva" in folded and "priloha" not in folded:
        return "CALL_DOCUMENT"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS or url in seen:
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


def _sentence(body: str, starts: tuple[str, ...]) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        folded = _normalize(sentence)
        if any(token in folded for token in starts):
            return _clean(sentence)
    return None


class MkAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="MKCR",
        name="Ministerstvo kultury — granty a dotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.mk.gov.cz/",
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF, RetrievalMode.DOCX, RetrievalMode.XLSX],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=360,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(CENTRAL_INDEX)
            healthy = (
                response.status_code == 200
                and "granty" in _normalize(response.text)
                and "dotace" in _normalize(response.text)
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected MK grant index: HTTP {response.status_code}"
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
        queue = [CENTRAL_INDEX]
        visited: set[str] = set()
        items: dict[str, DiscoveryItem] = {}

        while queue and len(visited) < _MAX_INDEX_PAGES:
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

            for title, url in _links(response.text, page_url):
                if _is_call_link(title, url, ctx.now):
                    ext = _external_id(title, url)
                    items[ext] = DiscoveryItem(
                        external_id=ext,
                        detail_url=url,
                        title_hint=title,
                        metadata={
                            "discovery_snapshot_id": snapshot_id,
                            "discovery_page": page_url,
                        },
                    )
                elif _is_index_link(title, ctx.now) and url not in visited and url not in queue:
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
            raise RuntimeError(f"MK detail returned HTTP {response.status_code}")

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
        closes = _deadline(body)

        code_match = re.search(r"výzva\s+č\.\s*(\d{3,5})", title, re.I)
        purpose = _sentence(body, ("cilem ", "vyzva je zameren", "ministerstvo kultury vyhlasuje"))
        applicants = _sentence(body, ("zadatelem ", "zadateli ", "opravneni zadatele"))
        application = _sentence(body, ("podani zadosti", "zadosti se podava", "prijem zadosti"))

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, closes),
                raw_fields={
                    "programme": "Ministerstvo kultury — národní dotace",
                    "callCode": code_match.group(1) if code_match else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "supportedActivitiesText": purpose,
                    "eligibleApplicantsText": applicants,
                    "applicationMethodText": application,
                    "coverageNote": (
                        "Connector discovers single-call pages from official MK grant indexes; "
                        "aggregate annual pages are discovery sources, not individual grants."
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
            raise RuntimeError(f"MK artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("MK adapter requires ctx.snapshots")
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
