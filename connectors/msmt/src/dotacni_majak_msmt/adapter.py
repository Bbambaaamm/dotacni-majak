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


MSMT_LISTING_URL = "https://msmt.gov.cz/dotace"
OPJAK_LISTING_URL = "https://opjak.cz/vyzvy/"
_MSMT_HOSTS = {"msmt.gov.cz", "www.msmt.gov.cz"}
_OPJAK_HOSTS = {"opjak.cz", "www.opjak.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")

_CZ_MONTHS = {
    "ledna": 1,
    "února": 2,
    "brezna": 3,
    "března": 3,
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


def _ascii_slug(value: str) -> str:
    # Keep IDs deterministic without relying on locale/transliteration packages.
    replacements = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    folded = value.translate(replacements).casefold()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def _datetime_from_date(
    year: int,
    month: int,
    day: int,
    *,
    end_of_day: bool = False,
) -> datetime:
    local = datetime.combine(
        datetime(year, month, day).date(),
        time(23, 59, 59) if end_of_day else time.min,
        tzinfo=_LOCAL_TZ,
    )
    return local.astimezone(timezone.utc)


def _parse_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    text = _clean(value)

    numeric = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b", text)
    if numeric:
        return _datetime_from_date(
            int(numeric.group(3)),
            int(numeric.group(2)),
            int(numeric.group(1)),
            end_of_day=end_of_day,
        )

    named = re.search(
        r"\b(\d{1,2})\.\s*([A-Za-zÁ-ž]+)\s+(20\d{2})\b",
        text,
        re.I,
    )
    if named:
        month = _CZ_MONTHS.get(named.group(2).casefold())
        if month is not None:
            return _datetime_from_date(
                int(named.group(3)),
                month,
                int(named.group(1)),
                end_of_day=end_of_day,
            )
    return None


def _status_from_dates(
    now: datetime,
    opens: datetime | None,
    closes: datetime | None,
) -> str:
    current = now.astimezone(timezone.utc)
    if closes is not None and current > closes:
        return "CLOSED"
    if opens is not None and current < opens:
        return "PLANNED"
    if opens is not None or closes is not None:
        return "OPEN"
    return "UNKNOWN"


def _explicit_status(value: str | None) -> str | None:
    if not value:
        return None
    folded = value.casefold()
    if "zruš" in folded:
        return "CANCELLED"
    if "ukončen" in folded:
        return "CLOSED"
    if "aktuál" in folded:
        return "OPEN"
    if "plán" in folded or "avíz" in folded:
        return "PLANNED"
    return None


def _label_value(text: str, label: str, next_labels: tuple[str, ...]) -> str | None:
    folded = text.casefold()
    start = folded.find(label.casefold())
    if start < 0:
        return None
    start += len(label)
    rest = text[start:].lstrip(" :\n\t")
    rest_folded = rest.casefold()
    stops = [
        rest_folded.find(next_label.casefold())
        for next_label in next_labels
        if rest_folded.find(next_label.casefold()) >= 0
    ]
    if stops:
        rest = rest[: min(stops)]
    return _clean(rest) or None


def _section_text(soup: BeautifulSoup, label: str) -> str | None:
    target = label.casefold()
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        if target not in _clean(heading.get_text(" ", strip=True)).casefold():
            continue
        parts: list[str] = []
        for element in heading.find_all_next():
            if (
                element is not heading
                and element.name
                and re.fullmatch(r"h[1-6]", element.name)
            ):
                break
            if element.name not in {"p", "li", "div"}:
                continue
            value = _clean(element.get_text(" ", strip=True))
            if value and value not in parts:
                parts.append(value)
        return "\n".join(parts) or None
    return None


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.casefold()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if path.endswith(".zip"):
        return "application/zip"
    return None


def _money_czk(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(
        r"([0-9]+(?:[\s.,][0-9]+)*)\s*(mil\.?|mld\.?|tis\.?)?\s*Kč",
        text,
        re.I,
    )
    if not match:
        return None
    raw = match.group(1).replace(" ", "").replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        return None
    unit = (match.group(2) or "").casefold()
    multiplier = 1
    if unit.startswith("tis"):
        multiplier = 1_000
    elif unit.startswith("mil"):
        multiplier = 1_000_000
    elif unit.startswith("mld"):
        multiplier = 1_000_000_000
    return int(round(amount * multiplier))


def _snapshot(
    ctx: AdapterContext,
    *,
    source_code: str,
    source_url: str,
    content: bytes,
    mime_type: str,
    headers: Any,
) -> str:
    if ctx.snapshots is None:
        raise RuntimeError(f"{source_code} adapter requires ctx.snapshots")
    snapshot = ctx.snapshots.put(
        source_code=source_code,
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


def _artifact_result(
    ctx: AdapterContext,
    *,
    source_code: str,
    artifact: RemoteArtifactRef,
    response: Any,
) -> ArtifactFetchResult:
    mime = response.headers.get(
        "content-type",
        artifact.mime_hint or "application/octet-stream",
    ).split(";", 1)[0]
    snapshot_id = _snapshot(
        ctx,
        source_code=source_code,
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


def _request_headers(validators: FetchValidators | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if validators:
        if validators.etag:
            headers["if-none-match"] = validators.etag
        if validators.last_modified:
            headers["if-modified-since"] = validators.last_modified
    return headers


# ---------------- MŠMT ----------------


def _msmt_external_id(title: str, url: str) -> str:
    cj = re.search(r"MSMT[-\s]?([0-9]+)/(20\d{2})(?:[-/]([0-9]+))?", title, re.I)
    if cj:
        suffix = f"-{cj.group(3)}" if cj.group(3) else ""
        return f"MSMT-{cj.group(1)}-{cj.group(2)}{suffix}"
    slug = _ascii_slug(PurePosixPath(urlsplit(url).path.rstrip("/")).name)
    return f"MSMT-{slug[:100]}" if slug else "MSMT-" + hashlib.sha256(url.encode()).hexdigest()[:20]


def _msmt_discovery(html: str) -> list[DiscoveryItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, DiscoveryItem] = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(MSMT_LISTING_URL, anchor["href"])
        parsed = urlsplit(url)
        if parsed.hostname not in _MSMT_HOSTS:
            continue
        if not parsed.path.startswith("/dotace/") or parsed.path.rstrip("/") == "/dotace":
            continue
        title = _clean(anchor.get_text(" ", strip=True))
        if not title or len(title) < 8:
            continue
        lowered = title.casefold()
        if (
            lowered.startswith("dodatek")
            or lowered.startswith("seznam podpořen")
            or lowered.startswith("výsledky")
        ):
            continue

        external_id = _msmt_external_id(title, url)
        container = anchor.find_parent(["article", "li", "div"])
        card_text = _clean(container.get_text(" ", strip=True)) if container else title
        created_match = re.search(r"Vytvořeno:\s*([^\n]+?20\d{2})", card_text, re.I)
        items[external_id] = DiscoveryItem(
            external_id=external_id,
            detail_url=url,
            title_hint=title,
            published_at_hint=_parse_date(created_match.group(1)) if created_match else None,
            metadata={"listingText": card_text},
        )
    return sorted(items.values(), key=lambda item: item.external_id)


def _msmt_artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    artifacts: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if urlsplit(url).hostname not in _MSMT_HOSTS or url in seen:
            continue
        mime = _mime_hint(url)
        if mime is None:
            continue
        seen.add(url)
        title = _clean(anchor.get_text(" ", strip=True)) or PurePosixPath(urlsplit(url).path).name
        lowered = title.casefold()
        normalized = _ascii_slug(title)
        if ("výzv" in lowered or "vyzv" in normalized) and "priloh" not in normalized:
            role = "CALL_DOCUMENT"
        elif (
            "žádost" in lowered
            or "zadost" in normalized
            or "formulář" in lowered
            or "formular" in normalized
        ):
            role = "APPLICATION_FORM"
        elif (
            "metodik" in lowered
            or "pravid" in lowered
            or "příruč" in lowered
            or "priruc" in normalized
        ):
            role = "GUIDELINES"
        else:
            role = "ANNEX"
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


class MsmtAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="MSMT",
        name="Ministerstvo školství, mládeže a tělovýchovy — národní dotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://msmt.gov.cz/",
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF, RetrievalMode.DOCX, RetrievalMode.XLSX],
        allowed_hosts=sorted(_MSMT_HOSTS),
        normal_refresh_minutes=360,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(MSMT_LISTING_URL)
            healthy = (
                response.status_code == 200
                and "dotace" in response.text.casefold()
                and bool(_msmt_discovery(response.text))
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected MŠMT listing: HTTP {response.status_code}"
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
        response = await ctx.http.get(MSMT_LISTING_URL)
        if response.status_code >= 400:
            raise RuntimeError(f"MŠMT listing returned HTTP {response.status_code}")
        snapshot_id = _snapshot(
            ctx,
            source_code=self.descriptor.code,
            source_url=MSMT_LISTING_URL,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        items = [
            item.model_copy(
                update={"metadata": {**item.metadata, "listing_snapshot_id": snapshot_id}}
            )
            for item in _msmt_discovery(response.text)
        ]
        return DiscoveryPage(items=items, next_checkpoint=None, is_complete=True, total_hint=len(items))

    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        response = await ctx.http.get(str(item.detail_url), headers=_request_headers(validators))
        if response.status_code == 304:
            return RecordFetchResult(state=FetchState.NOT_MODIFIED, http_status=304)
        if response.status_code == 404:
            return RecordFetchResult(state=FetchState.GONE, http_status=404)
        if response.status_code >= 400:
            raise RuntimeError(f"MŠMT detail returned HTTP {response.status_code}")

        snapshot_id = _snapshot(
            ctx,
            source_code=self.descriptor.code,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        title = _clean(h1.get_text(" ", strip=True)) if h1 else (item.title_hint or item.external_id)
        body = _clean(soup.get_text(" ", strip=True))

        status_text = _label_value(body, "Stav dotace", ("Typ projektu", "Určeno pro"))
        project_type = _label_value(body, "Typ projektu", ("Určeno pro",))
        audience = _label_value(body, "Určeno pro", ("Ministerstvo", "Výzva", "Ke stažení"))

        deadline_match = re.search(
            r"(?:nejpozději\s+)?do\s+"
            r"(\d{1,2}\.\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+)\s*20\d{2})",
            body,
            re.I,
        )
        closes = _parse_date(deadline_match.group(1), end_of_day=True) if deadline_match else None
        status = _explicit_status(status_text) or _status_from_dates(ctx.now, None, closes)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=status,
                published_at=item.published_at_hint,
                raw_fields={
                    "programme": "MŠMT — národní dotace",
                    "projectType": project_type,
                    "eligibleApplicantsText": audience,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "sourceBodyText": body,
                },
                artifacts=_msmt_artifacts(soup, str(item.detail_url)),
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
        response = await ctx.http.get(str(artifact.url), headers=_request_headers(validators))
        if response.status_code == 304:
            return ArtifactFetchResult(state=FetchState.NOT_MODIFIED)
        if response.status_code == 404:
            return ArtifactFetchResult(state=FetchState.GONE)
        if response.status_code >= 400:
            raise RuntimeError(f"MŠMT artifact returned HTTP {response.status_code}")
        return _artifact_result(ctx, source_code=self.descriptor.code, artifact=artifact, response=response)


# ---------------- OP JAK ----------------


def _opjak_external_id(title: str, url: str) -> str:
    code = re.search(r"\b(02_\d{2}_\d{3})\b", title)
    if code:
        return f"OPJAK-{code.group(1)}"
    slug = _ascii_slug(PurePosixPath(urlsplit(url).path.rstrip("/")).name)
    return f"OPJAK-{slug[:100]}" if slug else "OPJAK-" + hashlib.sha256(url.encode()).hexdigest()[:20]


def _opjak_discovery(html: str) -> list[DiscoveryItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, DiscoveryItem] = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(OPJAK_LISTING_URL, anchor["href"])
        parsed = urlsplit(url)
        if parsed.hostname not in _OPJAK_HOSTS or "/vyzvy/vyzva-" not in parsed.path:
            continue
        title = _clean(anchor.get_text(" ", strip=True))
        if not title:
            heading = anchor.find(["h2", "h3", "h4"])
            title = _clean(heading.get_text(" ", strip=True)) if heading else ""
        if not title or "výzva" not in title.casefold():
            continue

        container = anchor.find_parent(["article", "li", "div"])
        card_text = _clean(container.get_text(" ", strip=True)) if container else title
        opens_match = re.search(
            r"Datum zahájení příjmu žádostí[^:]*:?\s*"
            r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
            card_text,
            re.I,
        )
        closes_match = re.search(
            r"Datum ukončení příjmu žádost[^:]*:\s*"
            r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
            card_text,
            re.I,
        )
        allocation_match = re.search(
            r"Celková alokace\s+([^\n]+?Kč)",
            card_text,
            re.I,
        )
        external_id = _opjak_external_id(title, url)
        items[external_id] = DiscoveryItem(
            external_id=external_id,
            detail_url=url,
            title_hint=title,
            metadata={
                "submissionOpenAt": (
                    _parse_date(opens_match.group(1)).isoformat()
                    if opens_match and _parse_date(opens_match.group(1))
                    else None
                ),
                "submissionCloseAt": (
                    _parse_date(closes_match.group(1), end_of_day=True).isoformat()
                    if closes_match and _parse_date(closes_match.group(1), end_of_day=True)
                    else None
                ),
                "allocationCzk": _money_czk(allocation_match.group(1)) if allocation_match else None,
            },
        )
    return sorted(items.values(), key=lambda item: item.external_id)


def _opjak_artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    artifacts: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    current_role = "ANNEX"

    for element in soup.find_all([re.compile(r"^h[1-6]$"), "a"]):
        if element.name != "a":
            heading = _clean(element.get_text(" ", strip=True)).casefold()
            if "text výzvy" in heading:
                current_role = "CALL_DOCUMENT"
            elif "pravidla" in heading:
                current_role = "GUIDELINES"
            elif "faq" in heading or "časté dotazy" in heading:
                current_role = "FAQ"
            elif "příloh" in heading or "změn" in heading:
                current_role = "ANNEX"
            continue

        href = element.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if urlsplit(url).hostname not in _OPJAK_HOSTS or url in seen:
            continue
        mime = _mime_hint(url)
        if mime is None:
            continue
        seen.add(url)
        title = _clean(element.get_text(" ", strip=True)) or PurePosixPath(urlsplit(url).path).name
        artifacts.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=current_role,
                title=title,
                mime_hint=mime,
                required=(current_role == "CALL_DOCUMENT"),
            )
        )
    return artifacts


class OpJakAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="OPJAK",
        name="Operační program Jan Amos Komenský",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://opjak.cz/",
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF, RetrievalMode.DOCX, RetrievalMode.XLSX],
        allowed_hosts=sorted(_OPJAK_HOSTS),
        normal_refresh_minutes=240,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(OPJAK_LISTING_URL)
            healthy = (
                response.status_code == 200
                and "výzvy" in response.text.casefold()
                and bool(_opjak_discovery(response.text))
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected OP JAK listing: HTTP {response.status_code}"
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
        response = await ctx.http.get(OPJAK_LISTING_URL)
        if response.status_code >= 400:
            raise RuntimeError(f"OP JAK listing returned HTTP {response.status_code}")
        snapshot_id = _snapshot(
            ctx,
            source_code=self.descriptor.code,
            source_url=OPJAK_LISTING_URL,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        items = [
            item.model_copy(update={"metadata": {**item.metadata, "listing_snapshot_id": snapshot_id}})
            for item in _opjak_discovery(response.text)
        ]
        return DiscoveryPage(items=items, next_checkpoint=None, is_complete=True, total_hint=len(items))

    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        response = await ctx.http.get(str(item.detail_url), headers=_request_headers(validators))
        if response.status_code == 304:
            return RecordFetchResult(state=FetchState.NOT_MODIFIED, http_status=304)
        if response.status_code == 404:
            return RecordFetchResult(state=FetchState.GONE, http_status=404)
        if response.status_code >= 400:
            raise RuntimeError(f"OP JAK detail returned HTTP {response.status_code}")

        snapshot_id = _snapshot(
            ctx,
            source_code=self.descriptor.code,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        title = _clean(h1.get_text(" ", strip=True)) if h1 else (item.title_hint or item.external_id)
        body = _clean(soup.get_text(" ", strip=True))

        opens_match = re.search(
            r"Datum zahájení příjmu žádostí(?: o podporu)?\s*:?\s*"
            r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
            body,
            re.I,
        )
        closes_match = re.search(
            r"Datum ukončení příjmu žádost(?:i|í)(?: o podporu)?\s*:?\s*"
            r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
            body,
            re.I,
        )
        opens = _parse_date(opens_match.group(1)) if opens_match else None
        closes = _parse_date(closes_match.group(1), end_of_day=True) if closes_match else None
        if opens is None and item.metadata.get("submissionOpenAt"):
            opens = datetime.fromisoformat(item.metadata["submissionOpenAt"])
        if closes is None and item.metadata.get("submissionCloseAt"):
            closes = datetime.fromisoformat(item.metadata["submissionCloseAt"])

        allocation_match = re.search(r"Celková alokace\s+([^\n]+?Kč)", body, re.I)
        allocation = (
            _money_czk(allocation_match.group(1))
            if allocation_match
            else item.metadata.get("allocationCzk")
        )

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status_from_dates(ctx.now, opens, closes),
                raw_fields={
                    "programme": "OP JAK 2021–2027",
                    "callCode": (
                        re.search(r"\b02_\d{2}_\d{3}\b", title).group(0)
                        if re.search(r"\b02_\d{2}_\d{3}\b", title)
                        else None
                    ),
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "allocationCzk": allocation,
                    "supportedActivitiesText": _section_text(soup, "Cíl výzvy"),
                    "eligibleApplicantsText": _section_text(soup, "Oprávnění žadatelé"),
                    "applicationMethodText": _section_text(soup, "Podání žádosti o podporu"),
                },
                artifacts=_opjak_artifacts(soup, str(item.detail_url)),
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
        response = await ctx.http.get(str(artifact.url), headers=_request_headers(validators))
        if response.status_code == 304:
            return ArtifactFetchResult(state=FetchState.NOT_MODIFIED)
        if response.status_code == 404:
            return ArtifactFetchResult(state=FetchState.GONE)
        if response.status_code >= 400:
            raise RuntimeError(f"OP JAK artifact returned HTTP {response.status_code}")
        return _artifact_result(ctx, source_code=self.descriptor.code, artifact=artifact, response=response)
