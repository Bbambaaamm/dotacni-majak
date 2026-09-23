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


FAMILY_INDEX_URL = (
    "https://mpsv.gov.cz/"
    "dotace-na-podporu-rodiny-pro-nestatni-neziskove-organizace-"
    "v-dotacnim-rizeni-rodina"
)
_ALLOWED_HOSTS = {"mpsv.gov.cz", "www.mpsv.gov.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")


def _social_index_url(year: int) -> str:
    return f"https://mpsv.gov.cz/financni-prostredky-pro-rok-{year}"


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _year_from_text(value: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", value)
    return int(match.group(1)) if match else None


def _date(value: str, *, end_of_day: bool = False) -> datetime | None:
    cleaned = re.sub(r"\s+", "", value)
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            day = datetime.strptime(cleaned, fmt).date()
            local = datetime.combine(
                day,
                time(23, 59, 59) if end_of_day else time.min,
                tzinfo=_LOCAL_TZ,
            )
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _submission_window(text: str) -> tuple[datetime | None, datetime | None]:
    start = close = None
    range_match = re.search(
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})\s*[–-]\s*"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
        text,
    )
    if range_match:
        start = _date(range_match.group(1))
        close = _date(range_match.group(2), end_of_day=True)

    # Later extensions override the originally announced close date.
    extensions = re.findall(
        r"(?:prodlouž\w*|prodluž\w*)\s+(?:až\s+)?do\s+"
        r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
        text,
        re.I,
    )
    if extensions:
        extended = _date(extensions[-1], end_of_day=True)
        if extended is not None:
            close = extended

    if close is None:
        closing = re.findall(
            r"(?:do|nejpozději\s+do)\s+"
            r"(\d{1,2}\.\s*\d{1,2}\.\s*20\d{2})",
            text,
            re.I,
        )
        if closing:
            close = _date(closing[-1], end_of_day=True)

    return start, close


def _status(
    now: datetime,
    start: datetime | None,
    close: datetime | None,
) -> str:
    current = now.astimezone(timezone.utc)
    if close is not None and current > close:
        return "CLOSED"
    if start is not None and current < start:
        return "PLANNED"
    if start is not None or close is not None:
        return "OPEN"
    return "UNKNOWN"


def _section_text(soup: BeautifulSoup, *labels: str) -> str | None:
    folded_labels = tuple(label.casefold() for label in labels)
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        heading_text = _clean(heading.get_text(" ", strip=True))
        folded = heading_text.casefold()
        if not any(label in folded for label in folded_labels):
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


def _max_grant_czk(text: str | None) -> int | None:
    if not text:
        return None
    values: list[int] = []
    for match in re.finditer(
        r"maximálně\s+(?:o\s+částku\s+)?"
        r"([0-9][0-9\s.]*)\s*Kč",
        text,
        re.I,
    ):
        digits = re.sub(r"\D", "", match.group(1))
        if digits:
            values.append(int(digits))
    return max(values) if values else None


def _family_items(html: str, current_year: int) -> list[DiscoveryItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, DiscoveryItem] = {}
    for anchor in soup.find_all("a", href=True):
        title = _clean(anchor.get_text(" ", strip=True))
        match = re.search(r"dotační\s+řízení\s+pro\s+rok\s+(20\d{2})", title, re.I)
        if not match:
            continue
        year = int(match.group(1))
        if year < current_year or year > current_year + 1:
            continue
        url = urljoin(FAMILY_INDEX_URL, anchor["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS:
            continue
        external_id = f"MPSV-RODINA-{year}"
        items[external_id] = DiscoveryItem(
            external_id=external_id,
            detail_url=url,
            title_hint=f"Rodina {year} — dotační řízení",
            metadata={
                "programme": "Rodina",
                "year": year,
                "discovery_method": "FAMILY_INDEX",
            },
        )
    return sorted(items.values(), key=lambda item: item.external_id)


def _social_items(html: str, year: int) -> list[DiscoveryItem]:
    base_url = _social_index_url(year)
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, DiscoveryItem] = {}
    for anchor in soup.find_all("a", href=True):
        title = _clean(anchor.get_text(" ", strip=True))
        lowered = title.casefold()
        if "dotační" not in lowered or "sociální" not in lowered:
            continue
        url = urljoin(base_url, anchor["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS:
            continue
        slug = PurePosixPath(urlsplit(url).path.rstrip("/")).name.casefold()
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
        external_id = (
            f"MPSV-SOC-{year}-{slug[:72]}"
            if slug
            else "MPSV-SOC-" + hashlib.sha256(url.encode()).hexdigest()[:20]
        )
        items[external_id] = DiscoveryItem(
            external_id=external_id,
            detail_url=url,
            title_hint=title,
            metadata={
                "programme": "Sociální služby",
                "year": year,
                "discovery_method": "SOCIAL_INDEX",
            },
        )
    return sorted(items.values(), key=lambda item: item.external_id)


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.casefold()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".docx"):
        return (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )
    if path.endswith(".xlsx"):
        return (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    if path.endswith(".zip"):
        return "application/zip"
    return None


def _artifact_role(title: str) -> str:
    lowered = title.casefold()
    if "metodik" in lowered or "příruč" in lowered:
        return "GUIDELINES"
    if "formulář" in lowered or "žádost" in lowered:
        return "APPLICATION_FORM"
    if "výzv" in lowered and "příloh" not in lowered:
        return "CALL_DOCUMENT"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    heading = None
    for candidate in soup.find_all(re.compile(r"^h[1-6]$")):
        if "dokument" in _clean(candidate.get_text(" ", strip=True)).casefold():
            heading = candidate
            break
    if heading is None:
        return []

    artifacts: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for element in heading.find_all_next():
        if (
            element is not heading
            and element.name
            and re.fullmatch(r"h[1-6]", element.name)
        ):
            break
        if element.name != "a" or not element.get("href"):
            continue
        url = urljoin(base_url, element["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS or url in seen:
            continue
        mime = _mime_hint(url)
        if mime is None:
            continue
        seen.add(url)
        title = (
            _clean(element.get_text(" ", strip=True))
            or PurePosixPath(urlsplit(url).path).name
        )
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


class MpsvAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="MPSV",
        name="Ministerstvo práce a sociálních věcí — národní dotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://mpsv.gov.cz/",
        retrieval_modes=[
            RetrievalMode.HTML,
            RetrievalMode.PDF,
            RetrievalMode.DOCX,
            RetrievalMode.XLSX,
        ],
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
            family = await ctx.http.get(FAMILY_INDEX_URL)
            social = await ctx.http.get(_social_index_url(ctx.now.year))
            family_ok = (
                family.status_code == 200
                and "dotační řízení" in family.text.casefold()
            )
            social_ok = (
                social.status_code == 200
                and "finanční prostředky" in social.text.casefold()
            )
            if family_ok and social_ok:
                status = HealthStatus.HEALTHY
                detail = None
            elif family_ok or social_ok:
                status = HealthStatus.DEGRADED
                detail = "One MPSV seed index is unavailable or structurally unexpected."
            else:
                status = HealthStatus.UNAVAILABLE
                detail = "MPSV seed indexes are unavailable."
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
        items: dict[str, DiscoveryItem] = {}

        family_response = await ctx.http.get(FAMILY_INDEX_URL)
        if family_response.status_code >= 400:
            raise RuntimeError(
                f"MPSV family index returned HTTP {family_response.status_code}"
            )
        family_snapshot = self._snapshot(
            ctx,
            source_url=FAMILY_INDEX_URL,
            content=family_response.content,
            mime_type=family_response.headers.get(
                "content-type", "text/html"
            ).split(";", 1)[0],
            headers=family_response.headers,
        )
        for item in _family_items(family_response.text, ctx.now.year):
            items[item.external_id] = item.model_copy(
                update={
                    "metadata": {
                        **item.metadata,
                        "listing_snapshot_id": family_snapshot,
                    }
                }
            )

        social_url = _social_index_url(ctx.now.year)
        social_response = await ctx.http.get(social_url)
        if social_response.status_code < 400:
            social_snapshot = self._snapshot(
                ctx,
                source_url=social_url,
                content=social_response.content,
                mime_type=social_response.headers.get(
                    "content-type", "text/html"
                ).split(";", 1)[0],
                headers=social_response.headers,
            )
            for item in _social_items(social_response.text, ctx.now.year):
                items[item.external_id] = item.model_copy(
                    update={
                        "metadata": {
                            **item.metadata,
                            "listing_snapshot_id": social_snapshot,
                        }
                    }
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
            return RecordFetchResult(
                state=FetchState.NOT_MODIFIED,
                http_status=304,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
        if response.status_code == 404:
            return RecordFetchResult(
                state=FetchState.GONE,
                http_status=404,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"MPSV detail returned HTTP {response.status_code}"
            )

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get(
                "content-type", "text/html"
            ).split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        page_title = (
            _clean(h1.get_text(" ", strip=True))
            if h1 is not None
            else (item.title_hint or item.external_id)
        )
        body = _clean(soup.get_text(" ", strip=True))
        start, close = _submission_window(body)
        status = _status(ctx.now, start, close)

        focus = _section_text(
            soup,
            "věcné zaměření výzvy",
            "účel dotace",
        )
        applicants = _section_text(
            soup,
            "oprávnění žadatelé",
            "oprávnění žadatelé o dotaci",
        )
        application = _section_text(
            soup,
            "žádost o dotaci",
            "způsob podání",
        )
        attachments = _section_text(
            soup,
            "povinné přílohy",
        )
        programme = str(item.metadata.get("programme") or "MPSV")
        year = item.metadata.get("year") or _year_from_text(page_title)

        record = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title=(
                f"{programme} {year} — {page_title}"
                if year and programme.casefold() not in page_title.casefold()
                else page_title
            ),
            native_status=status,
            raw_fields={
                "programme": programme,
                "year": year,
                "supportedActivitiesText": focus,
                "eligibleApplicantsText": applicants,
                "applicationMethodText": application,
                "requiredAttachmentsText": attachments,
                "submissionOpenAt": start.isoformat() if start else None,
                "submissionCloseAt": close.isoformat() if close else None,
                "grantAmountMaxCzk": _max_grant_czk(application),
                "coverageNote": (
                    "Connector covers configured official MPSV programme "
                    "indexes; it does not claim complete MPSV coverage."
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
                f"MPSV artifact returned HTTP {response.status_code}"
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
            raise RuntimeError("MPSV adapter requires ctx.snapshots")
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
