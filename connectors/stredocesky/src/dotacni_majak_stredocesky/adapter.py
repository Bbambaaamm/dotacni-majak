from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pypdf import PdfReader

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


ROOT_URL = "https://stredoceskykraj.cz/web/urad/dotace"
_ALLOWED_HOSTS = {"stredoceskykraj.cz", "www.stredoceskykraj.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_COVERAGE = "LIMITED_STREDOCESKE_FONDY_GUIDE"
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
_DATE_RE = re.compile(
    r"(?P<d>\d{1,2})\.\s*"
    r"(?P<m>ledna|února|unora|března|brezna|dubna|května|kvetna|"
    r"června|cervna|července|cervence|srpna|září|zari|října|rijna|"
    r"listopadu|prosince)"
    r"(?:\s+(?P<y>20\d{2}))?"
    r"(?:\s*(?:od|v)?\s*(?P<h>\d{1,2})[:.](?P<minute>[0-5]\d))?",
    re.I,
)


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    return (
        value.translate(
            str.maketrans(
                "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
                "acdeeinorstuuyzACDEEINORSTUUYZ",
            )
        )
        .casefold()
    )


def _same_origin(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in _ALLOWED_HOSTS


def _find_guide_url(html: str, base_url: str = ROOT_URL) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if not _same_origin(url):
            continue
        label = _normalize(_clean(anchor.get_text(" ", strip=True)))
        path = _normalize(urlsplit(url).path)
        score = 0
        if "priruck" in label:
            score += 6
        if "prehled aktualne vyhlasenych programu" in label:
            score += 4
        if "sf_prirucka" in path:
            score += 8
        if "/documents/" in path or "/documents/d/" in path:
            score += 1
        if score:
            candidates.append((score, url))
    if not candidates:
        raise ValueError("official Středočeský funds guide link was not found")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _extract_pdf_pages(content: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(_clean(text))
    return pages


def _field(text: str, label: str, next_labels: tuple[str, ...]) -> str | None:
    folded = _normalize(text)
    start_marker = _normalize(label)
    start = folded.find(start_marker)
    if start < 0:
        return None
    start += len(start_marker)
    end = len(text)
    for next_label in next_labels:
        marker = _normalize(next_label)
        pos = folded.find(marker, start)
        if 0 <= pos < end:
            end = pos
    value = _clean(text[start:end]).strip(" :;-")
    return value or None


def _intro(text: str) -> str:
    folded = _normalize(text)
    cut = folded.find(_normalize("Lhůta pro podávání žádostí"))
    if cut < 0:
        cut = min(len(text), 700)
    return _clean(text[:cut])[:700]


def _fund_name(text: str) -> str:
    lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]
    for line in lines[:12]:
        folded = _normalize(line)
        if "fond" in folded and len(line) <= 140:
            return _clean(line)
    intro = _intro(text)
    match = re.search(r"((?:Středočeský\s+)?[^.]{0,100}Fond[^.]{0,100})", intro, re.I)
    return _clean(match.group(1))[:180] if match else "Středočeský fond"


def _title(text: str) -> str:
    intro = _intro(text)
    fund = _fund_name(text)
    descriptor = re.sub(r"\s+", " ", intro)
    descriptor = re.sub(r"^.*?" + re.escape(fund), "", descriptor, count=1, flags=re.I).strip()
    descriptor = re.sub(r"\s+stanov(?:uje|ují)\s*$", "", descriptor, flags=re.I)
    if descriptor:
        return _clean(f"{fund} — {descriptor}")[:500]
    return fund[:500]


def _parse_window(value: str | None) -> tuple[datetime | None, datetime | None]:
    if not value:
        return None, None
    matches = list(_DATE_RE.finditer(value))
    if len(matches) < 2:
        return None, None
    first, second = matches[0], matches[1]
    y2 = second.group("y")
    y1 = first.group("y") or y2
    if not y1 or not y2:
        return None, None

    def build(match: re.Match[str], year: int, closing: bool) -> datetime:
        month_key = _normalize(match.group("m"))
        month = _MONTHS.get(match.group("m").casefold()) or _MONTHS.get(month_key)
        if month is None:
            raise ValueError(f"unsupported Czech month: {match.group('m')}")
        hour = int(match.group("h")) if match.group("h") else (23 if closing else 0)
        minute = int(match.group("minute")) if match.group("minute") else (59 if closing else 0)
        second_value = 59 if closing and not match.group("h") else 0
        local = datetime(
            year,
            month,
            int(match.group("d")),
            hour,
            minute,
            second_value,
            tzinfo=_LOCAL_TZ,
        )
        return local.astimezone(timezone.utc)

    return build(first, int(y1), False), build(second, int(y2), True)


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    if opens is None or closes is None:
        return "ANNOUNCED"
    current = now.astimezone(timezone.utc)
    if current < opens:
        return "PLANNED"
    if current > closes:
        return "CLOSED"
    return "OPEN"


def _entry_from_page(
    *,
    page_text: str,
    page_number: int,
    guide_url: str,
    guide_snapshot_id: str,
    root_snapshot_id: str,
    guide_sha256: str,
    now: datetime,
) -> DiscoveryItem | None:
    folded = _normalize(page_text)
    if "lhuta pro podavani zadosti" not in folded:
        return None
    if "vyska dotace" not in folded and "predpokladana alokace" not in folded:
        return None

    title = _title(page_text)
    intro = _intro(page_text)
    identity_material = _normalize(title)
    external_id = "STC-" + hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:18]

    window = _field(
        page_text,
        "Lhůta pro podávání žádostí",
        (
            "Předpokládaná alokace programu",
            "Tematické zadání",
            "Oprávnění žadatelé",
            "Výše dotace",
        ),
    )
    allocation = _field(
        page_text,
        "Předpokládaná alokace programu",
        ("Tematické zadání", "Oprávnění žadatelé", "Výše dotace"),
    )
    applicants = _field(
        page_text,
        "Oprávnění žadatelé",
        ("Výše dotace", "Spoluúčast žadatele", "Bližší informace"),
    )
    grant_amount = _field(
        page_text,
        "Výše dotace",
        ("Spoluúčast žadatele", "Bližší informace", "Kontaktní osoba"),
    )
    cofinancing = _field(
        page_text,
        "Spoluúčast žadatele",
        ("Bližší informace", "Kontaktní osoba"),
    )
    opens, closes = _parse_window(window)

    record_hash = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
    return DiscoveryItem(
        external_id=external_id,
        detail_url=f"{guide_url}#page={page_number}",
        title_hint=title,
        native_status_hint=_status(now, opens, closes),
        metadata={
            "guide_url": guide_url,
            "guide_snapshot_id": guide_snapshot_id,
            "root_snapshot_id": root_snapshot_id,
            "guide_sha256": guide_sha256,
            "record_hash": record_hash,
            "source_page": page_number,
            "intro_text": intro,
            "page_text": page_text[:30000],
            "submission_window_text": window,
            "submission_open_at": opens.isoformat() if opens else None,
            "submission_close_at": closes.isoformat() if closes else None,
            "allocation_text": allocation,
            "applicant_text": applicants,
            "grant_amount_text": grant_amount,
            "cofinancing_text": cofinancing,
            "region_code": "CZ020",
            "coverage": _COVERAGE,
        },
    )


def entries_from_page_texts(
    pages: list[str],
    *,
    guide_url: str,
    guide_snapshot_id: str,
    root_snapshot_id: str,
    guide_sha256: str,
    now: datetime,
) -> list[DiscoveryItem]:
    items: dict[str, DiscoveryItem] = {}
    for index, page_text in enumerate(pages, start=1):
        item = _entry_from_page(
            page_text=page_text,
            page_number=index,
            guide_url=guide_url,
            guide_snapshot_id=guide_snapshot_id,
            root_snapshot_id=root_snapshot_id,
            guide_sha256=guide_sha256,
            now=now,
        )
        if item is not None:
            items[item.external_id] = item
    return sorted(items.values(), key=lambda item: item.external_id)


class StredoceskyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="STC",
        name="Středočeský kraj — Příručka středočeských fondů",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url=ROOT_URL,
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF],
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
            response = await ctx.http.get(ROOT_URL)
            healthy = (
                response.status_code == 200
                and "dotac" in _normalize(response.text)
                and "priruck" in _normalize(response.text)
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected Středočeský dotace page: HTTP {response.status_code}"
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
        root = await ctx.http.get(ROOT_URL)
        if root.status_code >= 400:
            raise RuntimeError(f"Středočeský dotace page returned HTTP {root.status_code}")
        root_snapshot_id = self._snapshot(
            ctx,
            source_url=ROOT_URL,
            content=root.content,
            mime_type=root.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=root.headers,
        )

        guide_url = _find_guide_url(root.text)
        guide = await ctx.http.get(guide_url)
        if guide.status_code >= 400:
            raise RuntimeError(f"Středočeský guide returned HTTP {guide.status_code}")
        mime = guide.headers.get("content-type", "application/pdf").split(";", 1)[0]
        if mime != "application/pdf" and not urlsplit(guide_url).path.casefold().endswith(".pdf"):
            # Liferay document routes can omit .pdf while still returning PDF.
            if not guide.content.startswith(b"%PDF"):
                raise ValueError(f"official guide is not a PDF: {mime}")

        guide_snapshot_id = self._snapshot(
            ctx,
            source_url=guide_url,
            content=guide.content,
            mime_type="application/pdf",
            headers=guide.headers,
        )
        guide_sha256 = hashlib.sha256(guide.content).hexdigest()
        pages = _extract_pdf_pages(guide.content)
        items = entries_from_page_texts(
            pages,
            guide_url=guide_url,
            guide_snapshot_id=guide_snapshot_id,
            root_snapshot_id=root_snapshot_id,
            guide_sha256=guide_sha256,
            now=ctx.now,
        )
        if not items:
            raise ValueError("official Středočeský guide produced zero grant candidates")

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
        record_hash = str(item.metadata.get("record_hash") or "")
        if validators and validators.known_sha256 and validators.known_sha256 == record_hash:
            return RecordFetchResult(state=FetchState.NOT_MODIFIED, http_status=304)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=item.title_hint,
                native_status=item.native_status_hint,
                raw_fields={
                    "supportedActivitiesText": item.metadata.get("page_text"),
                    "submissionWindowText": item.metadata.get("submission_window_text"),
                    "submissionOpenAt": item.metadata.get("submission_open_at"),
                    "submissionCloseAt": item.metadata.get("submission_close_at"),
                    "allocationText": item.metadata.get("allocation_text"),
                    "applicantText": item.metadata.get("applicant_text"),
                    "grantAmountText": item.metadata.get("grant_amount_text"),
                    "cofinancingText": item.metadata.get("cofinancing_text"),
                    "regionCode": item.metadata.get("region_code"),
                    "sourceDocumentUrl": item.metadata.get("guide_url"),
                    "sourcePage": item.metadata.get("source_page"),
                    "coverage": item.metadata.get("coverage"),
                    "coverageNote": (
                        "LIMITED coverage: only programmes explicitly listed in the "
                        "current official Středočeské fondy guide are monitored; "
                        "protected EDP is not bypassed."
                    ),
                    "recordHash": record_hash,
                },
                artifacts=[],
                snapshot_ids=[
                    str(item.metadata.get("root_snapshot_id")),
                    str(item.metadata.get("guide_snapshot_id")),
                ],
            ),
            http_status=200,
            etag=item.metadata.get("guide_sha256"),
        )

    async def fetch_artifact(
        self,
        ctx: AdapterContext,
        artifact: RemoteArtifactRef,
        validators: FetchValidators | None = None,
    ) -> ArtifactFetchResult:
        url = str(artifact.url)
        if not _same_origin(url):
            raise ValueError("Středočeský artifact must stay on official county host")
        headers: dict[str, str] = {}
        if validators:
            if validators.etag:
                headers["if-none-match"] = validators.etag
            if validators.last_modified:
                headers["if-modified-since"] = validators.last_modified
        response = await ctx.http.get(url, headers=headers)
        if response.status_code == 304:
            return ArtifactFetchResult(state=FetchState.NOT_MODIFIED)
        if response.status_code == 404:
            return ArtifactFetchResult(state=FetchState.GONE)
        if response.status_code >= 400:
            raise RuntimeError(f"Středočeský artifact returned HTTP {response.status_code}")
        mime = response.headers.get(
            "content-type", artifact.mime_hint or "application/octet-stream"
        ).split(";", 1)[0]
        snapshot_id = self._snapshot(
            ctx,
            source_url=url,
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
            raise RuntimeError("Středočeský adapter requires ctx.snapshots")
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
