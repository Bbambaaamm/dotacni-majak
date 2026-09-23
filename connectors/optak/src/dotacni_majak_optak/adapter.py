from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
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


LISTING_URL = "https://apiagentura.gov.cz/cs/radce/vsechny-vyzvy/"
_ALLOWED_HOSTS = {"apiagentura.gov.cz", "www.apiagentura.gov.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = _clean(value)
    for fmt in (
        "%d. %m. %Y %H:%M:%S",
        "%d. %m. %Y %H:%M",
        "%d. %m. %Y",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(cleaned, fmt).replace(
                tzinfo=_LOCAL_TZ
            ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _slug_id(url: str) -> str:
    slug = PurePosixPath(urlsplit(url).path.rstrip("/")).name.casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    if slug:
        return f"OPTAK-{slug[:100]}"
    return "OPTAK-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _discover_rows(html: str) -> list[DiscoveryItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, DiscoveryItem] = {}

    current_status: str | None = None
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "table"]):
        if element.name != "table":
            heading = _clean(element.get_text(" ", strip=True)).casefold()
            if heading == "otevřené výzvy":
                current_status = "OPEN"
            elif heading == "uzavřené výzvy":
                current_status = "CLOSED"
            continue

        if current_status is None:
            continue

        for row in element.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 5:
                continue
            anchor = cells[3].find("a", href=True)
            if anchor is None:
                continue
            detail_url = urljoin(LISTING_URL, anchor["href"])
            parsed = urlsplit(detail_url)
            if parsed.hostname not in _ALLOWED_HOSTS:
                continue

            title = _clean(anchor.get_text(" ", strip=True))
            if not title:
                continue
            external_id = _slug_id(detail_url)
            items[external_id] = DiscoveryItem(
                external_id=external_id,
                detail_url=detail_url,
                title_hint=title,
                native_status_hint=current_status,
                published_at_hint=_parse_datetime(
                    _clean(cells[0].get_text(" ", strip=True))
                ),
                metadata={
                    "announcedAt": (
                        _parse_datetime(_clean(cells[0].get_text(" ", strip=True))).isoformat()
                        if _parse_datetime(_clean(cells[0].get_text(" ", strip=True)))
                        else None
                    ),
                    "submissionOpenAt": (
                        _parse_datetime(_clean(cells[1].get_text(" ", strip=True))).isoformat()
                        if _parse_datetime(_clean(cells[1].get_text(" ", strip=True)))
                        else None
                    ),
                    "submissionCloseAt": (
                        _parse_datetime(_clean(cells[2].get_text(" ", strip=True))).isoformat()
                        if _parse_datetime(_clean(cells[2].get_text(" ", strip=True)))
                        else None
                    ),
                    "activityFocus": _clean(cells[4].get_text(" ", strip=True)),
                    "listingStatus": current_status,
                },
            )
    return sorted(items.values(), key=lambda item: item.external_id)


def _heading_value(soup: BeautifulSoup, label: str) -> str | None:
    target = label.casefold()
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        text = _clean(heading.get_text(" ", strip=True)).casefold()
        if text != target:
            continue
        parts: list[str] = []
        for element in heading.find_all_next():
            if element is not heading and element.name and re.fullmatch(r"h[1-6]", element.name):
                break
            if element.name not in {"p", "li", "div"}:
                continue
            value = _clean(element.get_text(" ", strip=True))
            if value and value not in parts:
                parts.append(value)
        return "\n".join(parts) or None
    return None


def _segment(text: str, start_label: str, end_labels: tuple[str, ...]) -> str | None:
    folded = text.casefold()
    start = folded.find(start_label.casefold())
    if start < 0:
        return None
    start += len(start_label)
    rest = text[start:].strip()
    rest_folded = rest.casefold()
    stops = [
        rest_folded.find(label.casefold())
        for label in end_labels
        if rest_folded.find(label.casefold()) >= 0
    ]
    if stops:
        rest = rest[: min(stops)].strip()
    return _clean(rest) or None


def _support_rate(text: str | None) -> float | None:
    if not text:
        return None
    matches = re.findall(r"([0-9]+(?:[,.][0-9]+)?)\s*%", text)
    if not matches:
        return None
    return max(float(value.replace(",", ".")) for value in matches)


def _money_minor_czk(value: str, multiplier: int) -> int:
    amount = float(value.replace(",", "."))
    return int(round(amount * multiplier))


def _project_cost_limits(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    amounts: list[int] = []
    for match in re.finditer(
        r"([0-9]+(?:[,.][0-9]+)?)\s*(tis\.?|mil\.?)\s*Kč",
        text,
        re.I,
    ):
        multiplier = 1_000 if match.group(2).casefold().startswith("tis") else 1_000_000
        amounts.append(_money_minor_czk(match.group(1), multiplier))
    if not amounts:
        return None, None
    if len(amounts) == 1:
        return amounts[0], None
    return min(amounts), max(amounts)


def _detail_status(soup: BeautifulSoup, fallback: str | None) -> str:
    headings = {
        _clean(h.get_text(" ", strip=True)).casefold()
        for h in soup.find_all(re.compile(r"^h[1-6]$"))
    }
    if "otevřená výzva" in headings:
        return "OPEN"
    if "uzavřená výzva" in headings:
        return "CLOSED"
    if "plánovaná výzva" in headings:
        return "PLANNED"
    if "zrušená výzva" in headings:
        return "CANCELLED"
    return fallback or "UNKNOWN"


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


def _artifact_role(title: str, call_title: str) -> str:
    del call_title
    lowered = title.casefold()

    # Classify explicit rules/forms before the generic call-document rule.
    # API sometimes uses '-' and sometimes '–' in otherwise identical titles,
    # so exact title containment is intentionally avoided.
    if "pravidla pro žadatele" in lowered or "příručka" in lowered or "prirucka" in lowered:
        return "GUIDELINES"
    if "formulář" in lowered or ("žádost" in lowered and "výzva" not in lowered):
        return "APPLICATION_FORM"
    if "faq" in lowered or "časté dotazy" in lowered:
        return "FAQ"
    if (
        "výzva" in lowered
        and "příloha" not in lowered
        and "pravidla" not in lowered
        and "archiv" not in lowered
    ):
        return "CALL_DOCUMENT"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str, call_title: str) -> list[RemoteArtifactRef]:
    heading = None
    for candidate in soup.find_all(re.compile(r"^h[1-6]$")):
        if _clean(candidate.get_text(" ", strip=True)).casefold() == "soubory":
            heading = candidate
            break
    if heading is None:
        return []

    artifacts: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for element in heading.find_all_next():
        if element is not heading and element.name and re.fullmatch(r"h[1-6]", element.name):
            break
        if element.name != "a" or not element.get("href"):
            continue
        url = urljoin(base_url, element["href"])
        parsed = urlsplit(url)
        if parsed.hostname not in _ALLOWED_HOSTS:
            continue
        mime = _mime_hint(url)
        if mime is None:
            continue
        if url in seen:
            continue
        seen.add(url)

        title = _clean(element.get_text(" ", strip=True)) or PurePosixPath(parsed.path).name
        role = _artifact_role(title, call_title)
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


class OpTakAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="OPTAK",
        name="OP TAK / Agentura pro podnikání a inovace",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://apiagentura.gov.cz/",
        retrieval_modes=[
            RetrievalMode.HTML,
            RetrievalMode.PDF,
            RetrievalMode.DOCX,
            RetrievalMode.XLSX,
        ],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=240,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(LISTING_URL)
            body = response.text.casefold()
            healthy = (
                response.status_code == 200
                and "výzvy op tak" in body
                and "otevřené výzvy" in body
                and "uzavřené výzvy" in body
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else f"Unexpected OP TAK listing: HTTP {response.status_code}"
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
        response = await ctx.http.get(LISTING_URL)
        if response.status_code >= 400:
            raise RuntimeError(f"OP TAK listing returned HTTP {response.status_code}")

        listing_snapshot = self._snapshot(
            ctx,
            source_url=LISTING_URL,
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )
        items = [
            item.model_copy(
                update={
                    "metadata": {
                        **item.metadata,
                        "listing_snapshot_id": listing_snapshot,
                    }
                }
            )
            for item in _discover_rows(response.text)
        ]
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
            return RecordFetchResult(
                state=FetchState.NOT_MODIFIED,
                http_status=304,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
        if response.status_code == 404:
            return RecordFetchResult(state=FetchState.GONE, http_status=404)
        if response.status_code >= 400:
            raise RuntimeError(f"OP TAK detail returned HTTP {response.status_code}")

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
            headers=response.headers,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        title = (
            _clean(h1.get_text(" ", strip=True))
            if h1 is not None
            else (item.title_hint or item.external_id)
        )
        body = _clean(soup.get_text(" ", strip=True))

        activities = _segment(
            body,
            "Na co lze získat podporu (podporované aktivity):",
            ("Kdo může žádat (příjemci podpory):",),
        )
        applicants = _segment(
            body,
            "Kdo může žádat (příjemci podpory):",
            ("Systém sběru žádostí:",),
        )
        collection = _segment(
            body,
            "Systém sběru žádostí:",
            ("Kolik lze získat na jeden projekt",),
        )
        project_amounts = _segment(
            body,
            "Kolik lze získat na jeden projekt",
            ("Míra podpory:",),
        )
        support = _segment(
            body,
            "Míra podpory:",
            ("Jaké výdaje je možné podpořit",),
        )
        eligible_costs = _segment(
            body,
            "Jaké výdaje je možné podpořit",
            ("Specifika a omezení:",),
        )
        restrictions = _segment(
            body,
            "Specifika a omezení:",
            ("Výstupy projektu:", "Soubory"),
        )
        min_cost, max_cost = _project_cost_limits(project_amounts)

        record = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title=title,
            native_status=_detail_status(soup, item.native_status_hint),
            published_at=item.published_at_hint,
            raw_fields={
                "programme": "OP TAK 2021–2027",
                "activityFocus": item.metadata.get("activityFocus"),
                "announcedAt": item.metadata.get("announcedAt"),
                "submissionOpenAt": item.metadata.get("submissionOpenAt"),
                "submissionCloseAt": item.metadata.get("submissionCloseAt"),
                "supportedActivitiesText": activities,
                "eligibleApplicantsText": applicants,
                "collectionSystemText": collection,
                "projectAmountText": project_amounts,
                "projectCostMinCzk": min_cost,
                "projectCostMaxCzk": max_cost,
                "supportRateMaxPercent": _support_rate(support),
                "eligibleCostsText": eligible_costs,
                "restrictionsText": restrictions,
            },
            artifacts=_artifacts(soup, str(item.detail_url), title),
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
            raise RuntimeError(f"OP TAK artifact returned HTTP {response.status_code}")

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
            raise RuntimeError("OP TAK adapter requires ctx.snapshots")
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
