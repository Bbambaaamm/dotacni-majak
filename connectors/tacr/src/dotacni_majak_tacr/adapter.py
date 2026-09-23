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


HOME = "https://tacr.gov.cz/"
PROGRAMMES = "https://tacr.gov.cz/programy-a-souteze/"
_ALLOWED_HOSTS = {"tacr.gov.cz", "www.tacr.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _tokens(soup: BeautifulSoup) -> list[str]:
    return [_clean(value) for value in soup.stripped_strings if _clean(value)]


def _value_after(tokens: list[str], *labels: str) -> str | None:
    normalized_labels = tuple(_normalize(label) for label in labels)
    for index, token in enumerate(tokens[:-1]):
        folded = _normalize(token)
        if any(folded == label or folded.startswith(label) for label in normalized_labels):
            return tokens[index + 1]
    return None


def _parse_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    match = re.search(
        r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})(?:\s*(?:v|ve)?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        value,
        re.I,
    )
    if not match:
        return None
    day, month, year = map(int, match.group(1, 2, 3))
    explicit_time = match.group(4) is not None
    if explicit_time:
        hour = int(match.group(4))
        minute = int(match.group(5) or 0)
        second = int(match.group(6) or 0)
    elif end_of_day:
        hour, minute, second = 23, 59, 59
    else:
        hour, minute, second = 0, 0, 0
    local = datetime(year, month, day, hour, minute, second, tzinfo=_LOCAL_TZ)
    return local.astimezone(timezone.utc)


def _submission_window(soup: BeautifulSoup) -> tuple[datetime | None, datetime | None]:
    body = _clean(soup.get_text(" ", strip=True))
    normalized = _normalize(body)

    open_match = re.search(
        r"soutezni lhuta zacina dnem\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})\s+"
        r"(?:v|ve)\s+(\d{1,2}:\d{2}(?::\d{2})?)",
        normalized,
        re.I,
    )
    opens = (
        _parse_date(f"{open_match.group(1)} {open_match.group(2)}")
        if open_match
        else None
    )

    close_date_match = re.search(
        r"soutezni lhuta[^.]{0,240}?konci dnem\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
        normalized,
        re.I,
    )
    closes = None
    if close_date_match:
        tail = normalized[close_date_match.end(): close_date_match.end() + 700]
        project_time = re.search(
            r"(\d{1,2}:\d{2}:\d{2})\s*hod\.?[^.]{0,180}?"
            r"nejzazsi[^.]{0,120}?podani navrhu projektu",
            tail,
            re.I,
        )
        if project_time:
            closes = _parse_date(
                f"{close_date_match.group(1)} {project_time.group(1)}"
            )

    summary = _value_after(
        _tokens(soup),
        "Lhůta pro podání návrhů projektů",
    )
    if summary:
        dates = re.findall(r"\d{1,2}\.\s*\d{1,2}\.\s*20\d{2}", summary)
        if opens is None and dates:
            opens = _parse_date(dates[0])
        if closes is None and len(dates) >= 2:
            closes = _parse_date(dates[1], end_of_day=True)

    return opens, closes


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes and current > closes:
        return "CLOSED"
    if opens or closes:
        return "OPEN"
    return "UNKNOWN"


def _external_id(title: str, url: str) -> str:
    slug = PurePosixPath(urlsplit(url).path.rstrip("/")).name
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize(slug)).strip("-")
    if normalized:
        return f"TACR-{normalized[:120]}"
    return "TACR-" + hashlib.sha256(f"{title}|{url}".encode()).hexdigest()[:24]


def _current_support_links(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(HOME, anchor["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS:
            continue
        if "/soutez/" not in urlsplit(url).path:
            continue
        title = _clean(anchor.get_text(" ", strip=True))
        folded = _normalize(title)
        if "bezi lhuta pro podavani navrhu projektu" not in folded:
            continue
        if url in seen:
            continue
        seen.add(url)
        visible_title = re.sub(
            r"\s*Běží lhůta pro podávání návrhů projektů\s*$",
            "",
            title,
            flags=re.I,
        )
        result.append((_clean(visible_title), url))
    return result


def _money(value: str | None) -> tuple[int | None, str | None]:
    if not value:
        return None, None
    match = re.search(
        r"([0-9][0-9\s.,]*)\s*(Kč|CZK|€|EUR)",
        value,
        re.I,
    )
    if not match:
        return None, None
    raw = match.group(1).replace(" ", "").replace("\xa0", "")
    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        return None, None
    currency = "CZK" if match.group(2).casefold() in {"kč", "czk"} else "EUR"
    return int(round(amount * 100)), currency


def _percent(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", value)
    if not match:
        return None
    return int(round(float(match.group(1).replace(",", ".")) * 100))


def _mime_hint(url: str) -> str | None:
    value = str(url).casefold()
    if ".pdf" in value:
        return "application/pdf"
    if ".docx" in value:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ".doc" in value:
        return "application/msword"
    if ".xlsx" in value or ".xlsm" in value:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if ".xls" in value:
        return "application/vnd.ms-excel"
    if ".zip" in value:
        return "application/zip"
    return None


def _artifact_role(title: str) -> str:
    folded = _normalize(title)
    if "zadavaci dokumentace" in folded or "call documentation" in folded:
        return "CALL_DOCUMENT"
    if "vseobecne podminky" in folded or "general terms" in folded or "priruck" in folded:
        return "GUIDELINES"
    if "formular" in folded or "application form" in folded:
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
        if mime is None:
            continue
        seen.add(url)
        role = _artifact_role(title)
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode()).hexdigest()[:24],
                url=url,
                role=role,
                title=title or PurePosixPath(urlsplit(url).path).name,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


class TacrAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="TACR",
        name="Technologická agentura ČR — aktuální možnosti podpory",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url=HOME,
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
            response = await ctx.http.get(HOME)
            healthy = (
                response.status_code == 200
                and "Aktuální možnosti podpory" in response.text
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected TAČR homepage: HTTP {response.status_code}"
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
        response = await ctx.http.get(HOME)
        if response.status_code >= 400:
            raise RuntimeError(f"TAČR homepage returned HTTP {response.status_code}")
        snapshot_id = self._snapshot(
            ctx,
            source_url=HOME,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        items = [
            DiscoveryItem(
                external_id=_external_id(title, url),
                detail_url=url,
                title_hint=title,
                native_status_hint="OPEN",
                metadata={
                    "discovery_snapshot_id": snapshot_id,
                    "discovery_page": HOME,
                },
            )
            for title, url in _current_support_links(response.text)
        ]
        items.sort(key=lambda item: item.external_id)
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
            raise RuntimeError(f"TAČR detail returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        tokens = _tokens(soup)
        h1 = soup.find("h1")
        title = _clean(h1.get_text(" ", strip=True)) if h1 else (item.title_hint or item.external_id)
        opens, closes = _submission_window(soup)

        allocation_text = _value_after(tokens, "Alokace")
        max_support_text = _value_after(tokens, "Maximální výše podpory na projekt")
        intensity_text = _value_after(tokens, "Maximální intenzita podpory na projekt")
        applicants = _value_after(tokens, "Uchazeči")
        result_date = _value_after(tokens, "Termín vyhlášení výsledků")

        allocation_minor, allocation_currency = _money(allocation_text)
        max_support_minor, max_support_currency = _money(max_support_text)

        body = _clean(soup.get_text(" ", strip=True))
        supported_match = re.search(
            r"(Veřejná soutěž[^.]{0,500}(?:zaměřena|zaměřená)[^.]{0,900}\.)",
            body,
            re.I,
        )

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(ctx.now, opens, closes),
                raw_fields={
                    "programme": title.split(":", 1)[0] if ":" in title else None,
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "resultAnnouncementText": result_date,
                    "allocationText": allocation_text,
                    "allocationAmountMinor": allocation_minor,
                    "allocationCurrency": allocation_currency,
                    "maxSupportAmountText": max_support_text,
                    "maxSupportAmountMinor": max_support_minor,
                    "maxSupportCurrency": max_support_currency,
                    "maxSupportIntensityBps": _percent(intensity_text),
                    "eligibleApplicantsText": applicants,
                    "supportedActivitiesText": (
                        _clean(supported_match.group(1)) if supported_match else None
                    ),
                    "applicationMethodText": (
                        "Návrh projektu se podává prostřednictvím SISTA; "
                        "přesné podmínky jsou na detailu soutěže a v zadávací dokumentaci."
                    ),
                    "coverageNote": (
                        "Discovery vychází z veřejné sekce Aktuální možnosti podpory TA ČR. "
                        "Plánované budoucí soutěže z harmonogramu jsou samostatná rozšiřující vrstva."
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
            raise RuntimeError(f"TAČR artifact returned HTTP {response.status_code}")
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
            raise RuntimeError("TAČR adapter requires ctx.snapshots")
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
