from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
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


ERASMUS_2026 = "https://www.dzs.cz/en/node/3607"
ESC_GRANTS = "https://www.dzs.cz/program/evropsky-sbor-solidarity/projekty-granty"
_ALLOWED_HOSTS = {"dzs.cz", "www.dzs.cz"}
_LOCAL_TZ = ZoneInfo("Europe/Prague")

_MONTHS = {
    "ledna": 1, "unora": 2, "února": 2, "brezna": 3, "března": 3,
    "dubna": 4, "kvetna": 5, "května": 5, "cervna": 6, "června": 6,
    "cervence": 7, "července": 7, "srpna": 8, "zari": 9, "září": 9,
    "rijna": 10, "října": 10, "listopadu": 11, "prosince": 12,
}


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalize(value)).strip("-")[:100]


def _parse_candidates(
    text: str,
    *,
    year: int,
    default_hour: int = 12,
) -> list[datetime]:
    found: list[tuple[int, int, int, int, int]] = []

    for match in re.finditer(
        r"(?<!\d)(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(20\d{2}))?"
        r"(?:\s*(?:v|ve|do)?\s*(\d{1,2}):(\d{2}))?",
        text,
        re.I,
    ):
        day, month = int(match.group(1)), int(match.group(2))
        value_year = int(match.group(3) or year)
        hour = int(match.group(4)) if match.group(4) else default_hour
        minute = int(match.group(5)) if match.group(5) else 0
        found.append((value_year, month, day, hour, minute))

    for match in re.finditer(
        r"(?<!\d)(\d{1,2})\.?\s+([A-Za-zÁ-ž]+)(?:\s+(20\d{2}))?"
        r"(?:\s*(?:v|ve|do)?\s*(\d{1,2}):(\d{2}))?",
        text,
        re.I,
    ):
        month = _MONTHS.get(match.group(2).casefold())
        if month is None:
            continue
        day = int(match.group(1))
        value_year = int(match.group(3) or year)
        hour = int(match.group(4)) if match.group(4) else default_hour
        minute = int(match.group(5)) if match.group(5) else 0
        found.append((value_year, month, day, hour, minute))

    unique: dict[tuple[int, int, int, int, int], datetime] = {}
    for parts in found:
        try:
            local = datetime(*parts, tzinfo=_LOCAL_TZ)
        except ValueError:
            continue
        unique[parts] = local.astimezone(timezone.utc)
    return sorted(unique.values())


def _select_deadline(
    candidates: list[datetime],
    now: datetime,
) -> datetime | None:
    if not candidates:
        return None
    current = now.astimezone(timezone.utc)
    future = [value for value in candidates if value >= current]
    return min(future) if future else max(candidates)


def _status(deadline: datetime | None, now: datetime) -> str:
    if deadline is None:
        return "UNKNOWN"
    return "OPEN" if deadline >= now.astimezone(timezone.utc) else "CLOSED"


def _nearest_sector(element: Any) -> str | None:
    heading = element.find_previous(["h2", "h3", "h4"])
    while heading is not None:
        text = _clean(heading.get_text(" ", strip=True))
        folded = _normalize(text)
        generic = (
            "terminy vyzvy" in folded
            or "terminy pro podavani" in folded
            or "seminar" in folded
            or "webinar" in folded
            or "konzultac" in folded
            or folded.startswith("klicova akce")
        )
        if not generic and text:
            if "mladez" in folded:
                return "Neformální vzdělávání mládeže"
            return text
        heading = heading.find_previous(["h2", "h3", "h4"])
    return None


def _action_name(text: str) -> str:
    value = text.split(":", 1)[0] if ":" in text else text
    value = re.split(
        r"\s+[–-]\s+(?=\d{1,2}(?:\.|\s))",
        value,
        maxsplit=1,
    )[0]
    value = re.sub(
        r"\s+(?:do\s+)?\d{1,2}\.?\s*(?:\d{1,2}\.|[A-Za-zÁ-ž]+).*$",
        "",
        value,
        flags=re.I,
    )
    return _clean(value).rstrip("–-: ")


def _opportunities_from_erasmus(
    html: str,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in soup.find_all("li"):
        text = _clean(item.get_text(" ", strip=True))
        if not text or re.match(r"^\d{1,2}[.\s]", text):
            continue
        dates = _parse_candidates(text, year=2026)
        if not dates:
            continue
        action = _action_name(text)
        folded = _normalize(action)
        grant_like = any(
            token in folded
            for token in (
                "akreditac",
                "vymena mladeze",
                "mobilita pracovniku",
                "aktivity participace",
                "discovereu",
                "kratkodob",
                "partnerstvi",
                "projekt mobilit",
                "kooperativ",
            )
        )
        if not grant_like or len(action) < 4:
            continue
        sector = _nearest_sector(item)
        deadline = _select_deadline(dates, now)
        external_id = f"DZS-ERASMUS-2026-{_slug((sector or '') + '-' + action)}"
        if external_id in seen:
            continue
        seen.add(external_id)
        result.append(
            {
                "external_id": external_id,
                "programme": "Erasmus+",
                "sector": sector,
                "action": action,
                "deadline": deadline,
                "deadline_text": text,
                "detail_url": ERASMUS_2026,
            }
        )
    return result


def _opportunities_from_esc(
    html: str,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in soup.find_all("li"):
        text = _clean(item.get_text(" ", strip=True))
        folded = _normalize(text)
        if not any(
            token in folded
            for token in (
                "solidarni projekty",
                "dobrovolnicke projekty",
                "dobrovolnicke tymy",
            )
        ):
            continue
        dates = _parse_candidates(text, year=2026)
        if not dates:
            continue
        action = _clean(text.split(":", 1)[0])
        deadline = _select_deadline(dates, now)
        external_id = f"DZS-ESC-2026-{_slug(action)}"
        if external_id in seen:
            continue
        seen.add(external_id)
        result.append(
            {
                "external_id": external_id,
                "programme": "Evropský sbor solidarity",
                "sector": None,
                "action": action,
                "deadline": deadline,
                "deadline_text": text,
                "detail_url": ESC_GRANTS,
            }
        )
    return result


class DzsAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="DZS",
        name="Dům zahraniční spolupráce — Erasmus+ a Evropský sbor solidarity",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.dzs.cz/",
        retrieval_modes=[RetrievalMode.HTML],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=360,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        failures: list[str] = []
        for url, marker in (
            (ERASMUS_2026, "Termíny výzvy 2026"),
            (ESC_GRANTS, "Termíny pro podávání žádostí"),
        ):
            try:
                response = await ctx.http.get(url)
                if response.status_code != 200 or marker not in response.text:
                    failures.append(f"{url}: HTTP {response.status_code}/marker")
            except Exception as exc:
                failures.append(f"{url}: {type(exc).__name__}: {exc}")
        elapsed = datetime.now(timezone.utc) - started
        return HealthReport(
            status=HealthStatus.HEALTHY if not failures else HealthStatus.DEGRADED,
            checked_at=ctx.now,
            latency_ms=max(0, int(elapsed.total_seconds() * 1000)),
            detail="; ".join(failures) if failures else None,
        )

    async def discover(
        self,
        ctx: AdapterContext,
        checkpoint: SourceCheckpoint | None,
    ) -> DiscoveryPage:
        del checkpoint
        opportunities: list[dict[str, Any]] = []

        for url, parser in (
            (ERASMUS_2026, _opportunities_from_erasmus),
            (ESC_GRANTS, _opportunities_from_esc),
        ):
            response = await ctx.http.get(url)
            if response.status_code >= 400:
                raise RuntimeError(f"DZS source returned HTTP {response.status_code}: {url}")
            snapshot_id = self._snapshot(
                ctx,
                source_url=url,
                content=response.content,
                mime_type=response.headers.get("content-type", "text/html").split(";", 1)[0],
                headers=response.headers,
            )
            for opportunity in parser(response.text, now=ctx.now):
                opportunity["snapshot_id"] = snapshot_id
                opportunities.append(opportunity)

        items = [
            DiscoveryItem(
                external_id=value["external_id"],
                detail_url=value["detail_url"],
                title_hint=(
                    f'{value["programme"]}: '
                    + (
                        f'{value["sector"]} — '
                        if value["sector"]
                        else ""
                    )
                    + value["action"]
                ),
                native_status_hint=_status(value["deadline"], ctx.now),
                metadata={
                    "programme": value["programme"],
                    "sector": value["sector"],
                    "action": value["action"],
                    "deadline": (
                        value["deadline"].isoformat()
                        if value["deadline"]
                        else None
                    ),
                    "deadline_text": value["deadline_text"],
                    "snapshot_id": value["snapshot_id"],
                },
            )
            for value in opportunities
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
        del validators
        deadline_raw = item.metadata.get("deadline")
        deadline = (
            datetime.fromisoformat(deadline_raw)
            if isinstance(deadline_raw, str) and deadline_raw
            else None
        )
        snapshot_id = item.metadata.get("snapshot_id")
        if not snapshot_id:
            raise RuntimeError("DZS discovery item is missing RAW snapshot_id")

        programme = str(item.metadata.get("programme") or "")
        sector = item.metadata.get("sector")
        action = str(item.metadata.get("action") or item.title_hint or item.external_id)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=item.title_hint,
                native_status=_status(deadline, ctx.now),
                raw_fields={
                    "programme": programme,
                    "sector": sector,
                    "action": action,
                    "submissionCloseAt": deadline.isoformat() if deadline else None,
                    "deadlineText": item.metadata.get("deadline_text"),
                    "fundingInstrumentType": "GRANT",
                    "applicationMethodText": (
                        "Podání probíhá prostřednictvím nástrojů EU/DZS podle konkrétní akce; "
                        "rozhodující jsou pokyny na oficiální stránce programu."
                    ),
                    "coverageNote": (
                        "Connector rozděluje veřejně uvedené termíny DZS na jednotlivé "
                        "grantové příležitosti. Centralizované aktivity EU mohou být pokryty "
                        "samostatně přes EU Funding & Tenders."
                    ),
                },
                artifacts=[],
                snapshot_ids=[str(snapshot_id)],
            ),
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
            raise RuntimeError(f"DZS artifact returned HTTP {response.status_code}")
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
            raise RuntimeError("DZS adapter requires ctx.snapshots")
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
