from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
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


INDEX_URL = "https://dotace.plzensky-kraj.cz/verejnost"
_ALLOWED_HOSTS = {"dotace.plzensky-kraj.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")
_DETAIL_RE = re.compile(r"/verejnost/dotacnititul/(\d+)/?$")


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _parse_local_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = _clean(value)
    match = re.search(
        r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})"
        r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        text,
    )
    if not match:
        return None
    day, month, year = map(int, match.group(1, 2, 3))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    second = int(match.group(6) or 0)
    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=_LOCAL_TZ,
    ).astimezone(timezone.utc)


def _grid_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        local = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_LOCAL_TZ)
    except ValueError:
        return None
    return local.astimezone(timezone.utc)


def _iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_LOCAL_TZ)
    return parsed.astimezone(timezone.utc)


def _status(now: datetime, opens: datetime | None, closes: datetime | None) -> str:
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes:
        return "CLOSED" if current > closes else "OPEN"
    return "UNKNOWN"


def _money_minor(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        return None
    return int(digits) * 100


def _table_value(soup: BeautifulSoup, labels: tuple[str, ...]) -> str | None:
    wanted = {_normalize(label) for label in labels}
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        key = _normalize(_clean(cells[0].get_text(" ", strip=True)))
        if key in wanted:
            return _clean(cells[1].get_text(" ", strip=True))
    return None


def _section_text(soup: BeautifulSoup, heading_names: tuple[str, ...]) -> str | None:
    wanted = {_normalize(name) for name in heading_names}
    for node in soup.find_all(["h1", "h2", "h3", "h4", "strong"]):
        label = _normalize(_clean(node.get_text(" ", strip=True)))
        if label not in wanted:
            continue
        chunks: list[str] = []
        for sibling in node.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h1", "h2", "h3", "h4"}:
                break
            if isinstance(sibling, Tag):
                text = _clean(sibling.get_text(" ", strip=True))
            else:
                text = _clean(str(sibling))
            if text:
                chunks.append(text)
            if len(" ".join(chunks)) > 4000:
                break
        value = _clean(" ".join(chunks))
        return value or None
    return None


def _mime_hint(url: str) -> str | None:
    path = urlsplit(url).path.casefold()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.endswith((".xlsx", ".xlsm")):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if "/soubor/" in path:
        return None
    return None


def _artifact_role(row_text: str) -> str:
    folded = _normalize(row_text)
    if "pravidla" in folded or "vyhlaseni" in folded:
        return "CALL_DOCUMENT"
    if "zadost" in folded or "formular" in folded:
        return "APPLICATION_FORM"
    if "podminky" in folded or "metodik" in folded:
        return "GUIDELINES"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
            continue
        if "/soubor/" not in parsed.path or url in seen:
            continue
        seen.add(url)
        row = anchor.find_parent("tr")
        context = _clean(row.get_text(" ", strip=True)) if row else _clean(anchor.get_text(" ", strip=True))
        role = _artifact_role(context)
        title = context or PurePosixPath(parsed.path.rstrip("/")).name
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                url=url,
                role=role,
                title=title[:500],
                mime_hint=_mime_hint(url),
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


class PlzenskyAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="PLK",
        name="Plzeňský kraj — eDotace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://dotace.plzensky-kraj.cz/",
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
                and "plzensky" in _normalize(response.text)
                and "dotacni" in _normalize(response.text)
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected eDotace index: HTTP {response.status_code}"
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
        items: dict[str, DiscoveryItem] = {}

        for grid_name, sort_name in _GRID_CONFIGS:
            url = (
                f"{INDEX_URL}?_name={grid_name}&page=1&rows=100"
                f"&sidx={sort_name}&sord=asc&_search=false"
            )
            response = await ctx.http.get(url)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Plzeň eDotace grid {grid_name} returned HTTP {response.status_code}"
                )

            snapshot_id = self._snapshot(
                ctx,
                source_url=url,
                content=response.content,
                mime_type=response.headers.get("content-type", "application/json").split(";", 1)[0],
                headers=response.headers,
            )

            try:
                payload = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Plzeň eDotace grid {grid_name} returned invalid JSON"
                ) from exc

            rows = payload.get("rows")
            if not isinstance(rows, list):
                raise RuntimeError(
                    f"Plzeň eDotace grid {grid_name} is missing rows[]"
                )

            for row in rows:
                cell = row.get("cell") if isinstance(row, dict) else None
                if not isinstance(cell, dict):
                    continue
                buttons = str(cell.get("buttons") or "")
                match = re.search(r"/verejnost/dotacnititul/(\d+)/", buttons)
                if not match:
                    continue

                numeric_id = int(match.group(1))
                external_id = f"PLK-{numeric_id}"
                detail_url = f"https://dotace.plzensky-kraj.cz/verejnost/dotacnititul/{numeric_id}/"
                title = _clean(str(cell.get("nazevtitulu") or cell.get("nazevprogramu") or external_id))
                opens = _grid_datetime(cell.get("zadostiod"))
                closes = _grid_datetime(cell.get("zadostido"))

                items[external_id] = DiscoveryItem(
                    external_id=external_id,
                    detail_url=detail_url,
                    title_hint=title,
                    native_status_hint=_status(ctx.now, opens, closes),
                    metadata={
                        "numeric_id": numeric_id,
                        "department": cell.get("nazevodboru"),
                        "programme": cell.get("nazevprogramu"),
                        "year": cell.get("roktitulu"),
                        "submission_open_at": opens.isoformat() if opens else None,
                        "submission_close_at": closes.isoformat() if closes else None,
                        "discovery_snapshot_id": snapshot_id,
                        "discovery_grid": grid_name,
                        "discovery_method": "official-public-jqgrid-json",
                    },
                )

        values = sorted(items.values(), key=lambda item: int(item.metadata["numeric_id"]))
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
            raise RuntimeError(f"Plzeň eDotace detail returned HTTP {response.status_code}")

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

        published = _parse_local_datetime(_table_value(soup, ("Zveřejnění",)))
        opens = (
            _parse_local_datetime(_table_value(soup, ("Žádosti od",)))
            or _iso_datetime(item.metadata.get("submission_open_at"))
        )
        closes = (
            _parse_local_datetime(_table_value(soup, ("Žádosti do",)))
            or _iso_datetime(item.metadata.get("submission_close_at"))
        )

        allocation = _money_minor(
            _table_value(soup, ("Předpokládaný celkový objem finančních prostředků",))
        )
        max_grant = _money_minor(
            _table_value(soup, ("Maximální požadovaná částka žadosti o dotaci",))
        )

        purpose = _section_text(soup, ("Účel podpory",))
        reason = _section_text(soup, ("Důvod podpory",))
        applicants = _section_text(soup, ("Potenciální žadatelé",))

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
                    "programme": item.metadata.get("programme") or "Plzeňský kraj — krajské dotační tituly",
                    "department": item.metadata.get("department"),
                    "sourceNumericId": item.metadata.get("numeric_id"),
                    "submissionOpenAt": opens.isoformat() if opens else None,
                    "submissionCloseAt": closes.isoformat() if closes else None,
                    "totalAllocationMinor": allocation,
                    "grantAmountMaxMinor": max_grant,
                    "supportedActivitiesText": purpose,
                    "supportReasonText": reason,
                    "eligibleApplicantsText": applicants,
                    "regionCode": "CZ032",
                    "regionName": "Plzeňský kraj",
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
            raise RuntimeError(f"Plzeň eDotace artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("Plzeňský adapter requires ctx.snapshots")
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
