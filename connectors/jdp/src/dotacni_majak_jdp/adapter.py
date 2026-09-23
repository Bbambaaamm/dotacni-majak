from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urljoin, urlsplit

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


BASE_URL = "https://jdp2.mf.gov.cz/"
API_BASE = "https://jdp2.mf.gov.cz/jdp_api/api/NxWebEDPPublicDashboard"
SEARCH_PATH = "/jdp_api/api/nxwebedppublicdashboard/kodyvyzva"
SEARCH_URL = "https://jdp2.mf.gov.cz" + SEARCH_PATH
STATUS_URL = API_BASE + "/KodyVyzvaStav"

_OPEN_FILTER = {
    "filterTree": {
        "filter": {
            "operator": "eq",
            "propName": "stavVyzvaLong",
            "value": "Běžící",
        }
    },
    "fixedFilterId": [],
    "fkName": "stavVyzvaLongWeb",
    "fkValue": "Otevřená",
    "pageIndex": 0,
    "pageSize": 50,
    "sort": [
        {
            "isDescending": False,
            "propName": "datumKonec",
            "treatNullLowest": False,
        }
    ],
}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    candidates = (
        raw,
        raw.replace("Z", "+00:00"),
    )
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            # JDP public API represents Czech local dates. Preserve the source
            # value in raw_fields; datetime hints remain deliberately naive-UTC
            # only for ordering until timezone normalization lands centrally.
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _money_minor(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _page_from_checkpoint(checkpoint: SourceCheckpoint | None) -> int:
    if checkpoint is None or not checkpoint.cursor:
        return 0
    try:
        page = int(checkpoint.cursor)
    except ValueError as exc:
        raise ValueError("JDP checkpoint cursor must be a zero-based page") from exc
    if page < 0:
        raise ValueError("JDP checkpoint cursor must be >= 0")
    return page


def _safe_public_link(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = urljoin(BASE_URL, value.strip())
    parsed = urlsplit(candidate)
    if parsed.scheme != "https":
        return None
    # The API may expose provider/application links outside JDP. Keep those
    # only as raw data; the source detail URL remains the JDP public portal.
    if parsed.hostname != "jdp2.mf.gov.cz":
        return None
    return candidate


class JdpAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="JDP",
        name="Jednotný dotační portál MF",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url=BASE_URL,
        retrieval_modes=[RetrievalMode.API, RetrievalMode.JSON],
        allowed_hosts=["jdp2.mf.gov.cz"],
        allowed_post_paths=[SEARCH_PATH],
        normal_refresh_minutes=240,
        max_concurrency=2,
        requests_per_second=1.0,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    def __init__(self, *, page_size: int = 50) -> None:
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        self.page_size = page_size

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(STATUS_URL)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"JDP status endpoint returned HTTP {response.status_code}"
                )
            payload = json.loads(response.text)
            states = payload.get("result") if isinstance(payload, dict) else None
            healthy = isinstance(states, list) and bool(states)
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else "Public JDP status list is empty or malformed"
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
        page_index = _page_from_checkpoint(checkpoint)
        request_payload = {
            **_OPEN_FILTER,
            "pageIndex": page_index,
            "pageSize": self.page_size,
        }

        response = await ctx.http.post_json(
            SEARCH_URL,
            payload=request_payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"JDP public call search returned HTTP {response.status_code}"
            )

        payload = json.loads(response.text)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("JDP public call search has no result object")

        records = result.get("items")
        if not isinstance(records, list):
            raise ValueError("JDP public call search has no items list")

        snapshot_id = self._snapshot(
            ctx,
            source_url=SEARCH_URL,
            content=response.content,
            mime_type=response.headers.get(
                "content-type",
                "application/json",
            ).split(";", 1)[0],
            headers=response.headers,
        )

        items: list[DiscoveryItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            external_id = record.get("id")
            if not isinstance(external_id, str) or not external_id.strip():
                continue

            native_status = record.get("stavVyzvaLongWeb")
            public_link = _safe_public_link(record.get("link"))
            detail_url = public_link or BASE_URL
            metadata = {
                "record": record,
                "discovery_snapshot_id": snapshot_id,
                "request_page_index": page_index,
                "coverage": "OPEN_PUBLIC_CALLS",
            }

            items.append(
                DiscoveryItem(
                    external_id=external_id,
                    detail_url=detail_url,
                    title_hint=record.get("nazev"),
                    native_status_hint=(
                        native_status if isinstance(native_status, str) else None
                    ),
                    metadata=metadata,
                )
            )

        has_next = bool(result.get("hasNextPage"))
        next_checkpoint = (
            SourceCheckpoint(cursor=str(page_index + 1))
            if has_next
            else None
        )
        total_hint = result.get("totalCount")
        if not isinstance(total_hint, int) or total_hint < 0:
            total_hint = None

        return DiscoveryPage(
            items=items,
            next_checkpoint=next_checkpoint,
            is_complete=not has_next,
            total_hint=total_hint,
        )

    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        record = item.metadata.get("record")
        snapshot_id = item.metadata.get("discovery_snapshot_id")
        if not isinstance(record, dict):
            raise ValueError("JDP discovery item has no source record payload")
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise RuntimeError("JDP discovery item has no RAW discovery snapshot")

        source_id = record.get("id")
        if source_id != item.external_id:
            raise ValueError("JDP discovery identity mismatch")

        open_at = _parse_datetime(record.get("datumZacatek"))
        close_at = _parse_datetime(record.get("datumKonec"))
        native_status = record.get("stavVyzvaLongWeb")
        public_link = _safe_public_link(record.get("link"))

        raw_fields = {
            "code": record.get("kod"),
            "description": record.get("popis"),
            "fundId": record.get("cedpKodyFond_id"),
            "nativeStatusCode": record.get("stavVyzva"),
            "nativeStatus": record.get("stavVyzvaLong"),
            "nativeStatusWeb": native_status,
            "instrumentType": record.get("typLong"),
            "submissionOpenAtSource": record.get("datumZacatek"),
            "submissionCloseAtSource": record.get("datumKonec"),
            "submissionOpenAt": open_at.isoformat() if open_at else None,
            "submissionCloseAt": close_at.isoformat() if close_at else None,
            "grantAmountMinSource": record.get("castkaPodporaZadostMin"),
            "grantAmountMaxSource": record.get("castkaPodporaZadostMax"),
            "allocationSource": record.get("castkaVyzvaCelkem"),
            "grantAmountMinMinor": _money_minor(record.get("castkaPodporaZadostMin")),
            "grantAmountMaxMinor": _money_minor(record.get("castkaPodporaZadostMax")),
            "allocationMinor": _money_minor(record.get("castkaVyzvaCelkem")),
            # Preserve the provider's value unchanged until the finance
            # normalization layer confirms its unit/scale.
            "supportRateMaxSource": record.get("miraPodporaZadostMax"),
            "taxRevenueMunicipalityAtDate": record.get("danovePrijmyObceKDatu"),
            "calculatorAvailable": record.get("zobrazitKalkulacku"),
            "publicLink": record.get("link"),
            "coverage": item.metadata.get("coverage"),
            "normalizedStatus": (
                "OPEN" if native_status == "Otevřená" else None
            ),
        }

        native = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item.external_id,
            detail_url=public_link or BASE_URL,
            native_title=(
                record.get("nazev")
                if isinstance(record.get("nazev"), str)
                else item.title_hint
            ),
            native_status=(
                native_status if isinstance(native_status, str) else None
            ),
            raw_fields=raw_fields,
            snapshot_ids=[snapshot_id],
        )

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=native,
            http_status=200,
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
                f"JDP artifact returned HTTP {response.status_code}"
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
        digest = hashlib.sha256(response.content).hexdigest()
        return ArtifactFetchResult(
            state=FetchState.MODIFIED,
            snapshot_id=snapshot_id,
            sha256=digest,
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
            raise RuntimeError(
                "JDP adapter requires ctx.snapshots for RAW-first ingestion"
            )
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
