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


NATIONAL_INDEX = "https://mze.gov.cz/public/portal/mze/vyhledavani/narodni-dotace"
SP_SCHEDULE = "https://mze.gov.cz/public/portal/mze/dotace/szp-pro-obdobi-2021-2027/harmonogram-vyzev"
_ALLOWED_HOSTS = {"mze.gov.cz", "www.mze.gov.cz", "szif.gov.cz", "www.szif.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_MAX_INDEX_PAGES = 10

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


def _parse_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    text = _clean(value)
    numeric = re.search(
        r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})(?:\s*(?:ve|v|do)?\s*(\d{1,2}):(\d{2}))?",
        text,
        re.I,
    )
    if numeric:
        day, month, year = map(int, numeric.group(1, 2, 3))
        hour = int(numeric.group(4)) if numeric.group(4) else (23 if end_of_day else 0)
        minute = int(numeric.group(5)) if numeric.group(5) else (59 if end_of_day else 0)
        second = 59 if end_of_day and not numeric.group(4) else 0
    else:
        named = re.search(
            r"\b(\d{1,2})\.?\s*([A-Za-zÁ-ž]+)\s+(20\d{2})(?:\s*(?:ve|v|do)?\s*(\d{1,2}):(\d{2}))?",
            text,
            re.I,
        )
        if not named:
            return None
        month = _CZ_MONTHS.get(named.group(2).casefold()) or _CZ_MONTHS.get(_normalize(named.group(2)))
        if month is None:
            return None
        day, year = int(named.group(1)), int(named.group(3))
        hour = int(named.group(4)) if named.group(4) else (23 if end_of_day else 0)
        minute = int(named.group(5)) if named.group(5) else (59 if end_of_day else 0)
        second = 59 if end_of_day and not named.group(4) else 0

    local = datetime(year, month, day, hour, minute, second, tzinfo=_LOCAL_TZ)
    return local.astimezone(timezone.utc)


def _submission_window(body: str) -> tuple[datetime | None, datetime | None]:
    open_patterns = (
        r"(?:příjem|prijem)\s+žádostí[^.]{0,120}?(?:začíná|zacina)\s+"
        r"(\d{1,2}\.?\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2}(?:\s*(?:ve|v)?\s*\d{1,2}:\d{2})?)",
        r"(?:podávání|podavani)\s+žádostí[^.]{0,120}?(?:od)\s+"
        r"(\d{1,2}\.?\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2}(?:\s*(?:ve|v)?\s*\d{1,2}:\d{2})?)",
    )
    close_patterns = (
        r"(?:ukončení|ukonceni)\s+(?:přijímání|prijimani)\s+žádostí\s*:\s*"
        r"(\d{1,2}\.?\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2}(?:\s*(?:ve|v|do)?\s*\d{1,2}:\d{2})?)",
        r"(?:příjem|prijem)\s+žádostí[^.]{0,140}?(?:končí|konci)\s+"
        r"(\d{1,2}\.?\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2}(?:\s*(?:ve|v|do)?\s*\d{1,2}:\d{2})?)",
        r"(?:nejpozději|nejpozdeji)\s+do[^,.;]{0,80}?"
        r"(\d{1,2}\.?\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2}(?:\s*(?:ve|v|do)?\s*\d{1,2}:\d{2})?)",
    )

    opens = None
    closes = None
    for pattern in open_patterns:
        match = re.search(pattern, body, re.I)
        if match:
            opens = _parse_datetime(match.group(1))
            if opens:
                break

    for pattern in close_patterns:
        match = re.search(pattern, body, re.I)
        if match:
            closes = _parse_datetime(match.group(1), end_of_day=True)
            if closes:
                break

    return opens, closes


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    utc_now = now.astimezone(timezone.utc)
    if opens and utc_now < opens:
        return "PLANNED"
    if closes and utc_now > closes:
        return "CLOSED"
    if opens or closes:
        return "OPEN"
    return "UNKNOWN"


def _year_relevant(text: str, now: datetime) -> bool:
    years = {int(value) for value in re.findall(r"\b20\d{2}\b", text)}
    if not years:
        return True
    return bool(years & {now.year - 1, now.year, now.year + 1})


def _is_result_or_admin(title: str) -> bool:
    folded = _normalize(title)
    blocked = (
        "seznam dotaci poskytnutych",
        "vysled",
        "zaver z prijmu",
        "konsolidovane zneni",
        "zpresneni zasad",
        "upozorneni",
        "metodicka prirucka",
        "formular",
        "archiv",
        "logo",
    )
    return any(token in folded for token in blocked)


def _is_call_link(title: str, url: str, now: datetime) -> bool:
    if not title or _is_result_or_admin(title) or not _year_relevant(title, now):
        return False
    folded = _normalize(title)
    path = _normalize(urlsplit(url).path)
    return (
        ("vyzva" in folded and ("zadost" in folded or "podpor" in folded or "dotac" in folded))
        or ("vyzva" in folded and "/dotace/" in path)
        or ("vyzva-" in path and "/dotace/" in path)
    )


def _external_id(title: str, url: str) -> str:
    folded = _normalize(title)
    if "nno" in folded or "nestatnich neziskovych organizaci" in folded:
        year = re.search(r"\b(20\d{2})\b", folded)
        if year:
            return f"MZE-NNO-{year.group(1)}"
    call = re.search(r"\b(\d{1,2})\.?\s*[-.]?\s*výzva\b", title, re.I)
    if call:
        year = re.search(r"\b(20\d{2})\b", title)
        suffix = f"-{year.group(1)}" if year else ""
        return f"MZE-CALL-{call.group(1)}{suffix}"
    slug = PurePosixPath(urlsplit(url).path.rstrip("/")).name
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize(slug)).strip("-")
    return f"MZE-{normalized[:100]}" if normalized else "MZE-" + hashlib.sha256(url.encode()).hexdigest()[:20]


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.casefold()
    query = urlsplit(url).query.casefold()
    combined = f"{path}?{query}"
    if ".pdf" in combined or "cmdocument" in path and "pdf" in query:
        return "application/pdf"
    if ".docx" in combined:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ".doc" in combined:
        return "application/msword"
    if ".xlsx" in combined or ".xlsm" in combined:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if ".xls" in combined:
        return "application/vnd.ms-excel"
    if ".zip" in combined:
        return "application/zip"
    return None


def _artifact_role(title: str) -> str:
    folded = _normalize(title)
    if "vyhlaseni" in folded or ("vyzva" in folded and "priloha" not in folded):
        return "CALL_DOCUMENT"
    if "zasad" in folded or "pravidl" in folded or "metodik" in folded or "priruck" in folded:
        return "GUIDELINES"
    if "zadost" in folded or "formular" in folded:
        return "APPLICATION_FORM"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS or url in seen:
            continue
        title = _clean(anchor.get_text(" ", strip=True))
        mime = _mime_hint(url)
        if mime is None and not any(token in _normalize(title) for token in ("stahnout", "priloha", "zasad", "vyhlaseni", "zadost")):
            continue
        if mime is None:
            continue
        seen.add(url)
        label = title or PurePosixPath(urlsplit(url).path).name or "Dokument"
        role = _artifact_role(label)
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=label,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


def _section_after_heading(soup: BeautifulSoup, labels: tuple[str, ...]) -> str | None:
    normalized_labels = tuple(_normalize(label) for label in labels)
    for element in soup.find_all(["h2", "h3", "h4", "strong", "p"]):
        heading = _clean(element.get_text(" ", strip=True))
        folded = _normalize(heading)
        if not any(label in folded for label in normalized_labels):
            continue
        sibling = element.find_next_sibling()
        while sibling is not None:
            if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4"}:
                break
            text = _clean(sibling.get_text(" ", strip=True)) if hasattr(sibling, "get_text") else ""
            if text:
                return text
            sibling = sibling.find_next_sibling()
    return None


class MzeSzifAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="MZE",
        name="Ministerstvo zemědělství / SZIF — veřejné dotační výzvy",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://mze.gov.cz/",
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
            response = await ctx.http.get(NATIONAL_INDEX)
            healthy = response.status_code == 200 and "národní dotace" in response.text.casefold()
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected MZe national grants index: HTTP {response.status_code}"
        except Exception as exc:
            status = HealthStatus.UNAVAILABLE
            detail = f"{type(exc).__name__}: {exc}"
        elapsed = datetime.now(timezone.utc) - started
        return HealthReport(
            status=status,
            checked_at=ctx.now,
            latency_ms=max(0, int(elapsed.total_seconds() * 1000)),
            detail=detail,
            diagnostics={
                "directSzifDiscovery": "unsupported-captcha-protected",
                "discoverySource": NATIONAL_INDEX,
                "strategicPlanSchedule": SP_SCHEDULE,
            },
        )

    async def discover(self, ctx: AdapterContext, checkpoint: SourceCheckpoint | None) -> DiscoveryPage:
        del checkpoint
        response = await ctx.http.get(NATIONAL_INDEX)
        if response.status_code >= 400:
            raise RuntimeError(f"MZe national index returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=NATIONAL_INDEX,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        items: dict[str, DiscoveryItem] = {}

        for anchor in soup.find_all("a", href=True):
            url = urljoin(NATIONAL_INDEX, anchor["href"])
            if urlsplit(url).hostname not in {"mze.gov.cz", "www.mze.gov.cz"}:
                continue
            title = _clean(anchor.get_text(" ", strip=True))
            if not _is_call_link(title, url, ctx.now):
                continue
            ext = _external_id(title, url)
            items[ext] = DiscoveryItem(
                external_id=ext,
                detail_url=url,
                title_hint=title,
                metadata={
                    "discovery_snapshot_id": snapshot_id,
                    "discovery_page": NATIONAL_INDEX,
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
            raise RuntimeError(f"MZe detail returned HTTP {response.status_code}")

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
        opens, closes = _submission_window(body)

        applicants = _section_after_heading(
            soup,
            ("Účastníci výběrového řízení", "Oprávnění žadatelé", "Žadatelé"),
        )
        supported = _section_after_heading(
            soup,
            ("Oblasti podpory", "Předmět dotace", "Účel dotace"),
        )
        application = _section_after_heading(
            soup,
            ("Způsob podání žádosti", "Podání žádosti"),
        )

        year = re.search(r"\b(20\d{2})\b", title)
        call_code = re.search(r"\b(?:výzva|vyzva)\s*(?:č\.?\s*)?(\d{1,3})\b", _normalize(title))

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                raw_fields={
                    "programme": "Ministerstvo zemědělství — veřejné dotace",
                    "callCode": call_code.group(1) if call_code else None,
                    "callYear": int(year.group(1)) if year else None,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "eligibleApplicantsText": applicants,
                    "supportedActivitiesText": supported,
                    "applicationMethodText": application,
                    "coverageNote": (
                        "Discovery používá veřejný portál MZe. Přímý seznam národních dotací "
                        "na SZIF je CAPTCHA-protected a není obcházen; dokumenty na szif.gov.cz "
                        "se stahují pouze tehdy, pokud jsou veřejně odkazované z oficiální stránky MZe."
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
            raise RuntimeError(f"MZe/SZIF artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("MZe/SZIF adapter requires ctx.snapshots")
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
