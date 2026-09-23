from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

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


PORTAL_BASE = "https://dotace.khk.cz/"
API_ORIGIN = "https://dotisreactfunctions.azurewebsites.net"
COLLECTION_PATH = "/api/Data/GetProjectSubprojectCollection"
DETAIL_PATH = "/api/Data/GetSubproject"
DOCUMENTS_PATH = "/api/Data/GetSubprojectDocumentCollection"
COLLECTION_URL = API_ORIGIN + COLLECTION_PATH
DETAIL_URL = API_ORIGIN + DETAIL_PATH
DOCUMENTS_URL = API_ORIGIN + DOCUMENTS_PATH

_LOCAL_TZ = ZoneInfo("Europe/Prague")
_ALLOWED_HOSTS = {"dotace.khk.cz", "dotisreactfunctions.azurewebsites.net"}


def _clean_html(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = html.unescape(value)
    text = re.sub(r"<br\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.replace("\xa0", " ").split())
    return text or None


def _parse_local_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_LOCAL_TZ)
    return parsed.astimezone(timezone.utc)


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


def _percent_bps(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not percent.is_finite() or percent < 0 or percent > 100:
        return None
    return int((percent * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalized_status(
    now: datetime,
    opens: datetime | None,
    closes: datetime | None,
) -> str | None:
    current = now.astimezone(timezone.utc)
    if opens and current < opens:
        return "PLANNED"
    if closes and current > closes:
        return "CLOSED"
    if opens or closes:
        return "OPEN"
    return None


def _years(ctx: AdapterContext) -> list[str]:
    local_year = ctx.now.astimezone(_LOCAL_TZ).year
    return [str(local_year + 1), str(local_year)]


def _envelope_data(payload: Any, *, endpoint: str) -> Any:
    if not isinstance(payload, dict):
        raise ValueError(f"KHK {endpoint} response is not an object")
    if payload.get("succeed") is False:
        raise ValueError(
            f"KHK {endpoint} returned succeed=false: {payload.get('errorMessage')!r}"
        )
    if "data" not in payload:
        raise ValueError(f"KHK {endpoint} response has no data field")
    return payload["data"]


def _document_metadata(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        doc_id = row.get("id_Document")
        title = row.get("title")
        if not isinstance(doc_id, int) or not isinstance(title, str):
            continue
        result.append(
            {
                "id": doc_id,
                "title": title,
                "note": row.get("note"),
                "extension": row.get("ext"),
                "sizeBytes": row.get("size"),
            }
        )
    return result


class KhkAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="KHK",
        name="Královéhradecký kraj — dotační portál",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url=PORTAL_BASE,
        retrieval_modes=[
            RetrievalMode.API,
            RetrievalMode.JSON,
            RetrievalMode.PDF,
            RetrievalMode.DOCX,
        ],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        allowed_post_paths=[
            COLLECTION_PATH,
            DETAIL_PATH,
            DOCUMENTS_PATH,
        ],
        normal_refresh_minutes=240,
        max_concurrency=2,
        requests_per_second=1.0,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            response = await ctx.http.get(PORTAL_BASE)
            healthy = (
                response.status_code == 200
                and "dotace" in response.text.casefold()
            )
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = (
                None
                if healthy
                else f"Unexpected KHK public portal response: HTTP {response.status_code}"
            )
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
        requested_years = _years(ctx)
        response = await ctx.http.post_json(
            COLLECTION_URL,
            payload={"year": requested_years},
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"KHK public programme collection returned HTTP {response.status_code}"
            )

        payload = json.loads(response.text)
        groups = _envelope_data(payload, endpoint="programme collection")
        if not isinstance(groups, list):
            raise ValueError("KHK programme collection data is not a list")

        snapshot_id = self._snapshot(
            ctx,
            source_url=COLLECTION_URL,
            content=response.content,
            mime_type=response.headers.get(
                "content-type", "application/json"
            ).split(";", 1)[0],
            headers=response.headers,
        )

        items: list[DiscoveryItem] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_code = group.get("memo")
            group_name = group.get("name")
            subprojects = group.get("subprojects")
            if not isinstance(subprojects, list):
                continue

            for row in subprojects:
                if not isinstance(row, dict):
                    continue
                subproject_id = row.get("id_Def_Subproject")
                code = row.get("memo")
                title = row.get("name")
                if not isinstance(subproject_id, int):
                    continue
                if not isinstance(code, str) or not code.strip():
                    continue
                if not isinstance(title, str) or not title.strip():
                    continue

                opens = _parse_local_datetime(row.get("dateBeg"))
                closes = _parse_local_datetime(row.get("dateEnd"))
                source_state = row.get("state")
                items.append(
                    DiscoveryItem(
                        external_id=f"KHK-{subproject_id}",
                        detail_url=f"{PORTAL_BASE}grantProgram/{code}",
                        title_hint=title.strip(),
                        native_status_hint=(
                            f"state:{source_state}"
                            if source_state is not None
                            else None
                        ),
                        published_at_hint=None,
                        updated_at_hint=None,
                        metadata={
                            "idDefSubproject": subproject_id,
                            "programCode": code,
                            "groupCode": group_code,
                            "groupName": group_name,
                            "sourceState": source_state,
                            "submissionOpenAtSource": row.get("dateBeg"),
                            "submissionCloseAtSource": row.get("dateEnd"),
                            "submissionOpenAt": (
                                opens.isoformat() if opens else None
                            ),
                            "submissionCloseAt": (
                                closes.isoformat() if closes else None
                            ),
                            "normalizedStatusHint": _normalized_status(
                                ctx.now, opens, closes
                            ),
                            "discoverySnapshotId": snapshot_id,
                            "requestedYears": requested_years,
                            "discoveryMethod": (
                                "public-GetProjectSubprojectCollection"
                            ),
                        },
                    )
                )

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
        subproject_id = item.metadata.get("idDefSubproject")
        code = item.metadata.get("programCode")
        discovery_snapshot_id = item.metadata.get("discoverySnapshotId")

        if not isinstance(subproject_id, int):
            raise ValueError("KHK item has no numeric idDefSubproject")
        if not isinstance(code, str) or not code:
            raise ValueError("KHK item has no programCode")
        if not isinstance(discovery_snapshot_id, str):
            raise RuntimeError("KHK item has no RAW discovery snapshot")

        detail_response = await ctx.http.post_json(
            DETAIL_URL,
            payload={"memo": code},
        )
        if detail_response.status_code >= 400:
            raise RuntimeError(
                f"KHK public detail returned HTTP {detail_response.status_code}"
            )
        detail_payload = json.loads(detail_response.text)
        detail = _envelope_data(detail_payload, endpoint="programme detail")
        if not isinstance(detail, dict):
            raise ValueError("KHK programme detail data is not an object")
        if detail.get("id_Def_Subproject") != subproject_id:
            raise ValueError("KHK detail identity mismatch")
        if detail.get("memo") != code:
            raise ValueError("KHK detail code mismatch")

        detail_snapshot_id = self._snapshot(
            ctx,
            source_url=DETAIL_URL,
            content=detail_response.content,
            mime_type=detail_response.headers.get(
                "content-type", "application/json"
            ).split(";", 1)[0],
            headers=detail_response.headers,
        )

        documents_response = await ctx.http.post_json(
            DOCUMENTS_URL,
            payload={"id_Def_Subproject": subproject_id},
        )
        if documents_response.status_code >= 400:
            raise RuntimeError(
                "KHK public document collection returned "
                f"HTTP {documents_response.status_code}"
            )
        documents_payload = json.loads(documents_response.text)
        documents = _document_metadata(
            _envelope_data(documents_payload, endpoint="document collection")
        )
        documents_snapshot_id = self._snapshot(
            ctx,
            source_url=DOCUMENTS_URL,
            content=documents_response.content,
            mime_type=documents_response.headers.get(
                "content-type", "application/json"
            ).split(";", 1)[0],
            headers=documents_response.headers,
        )

        opens = _parse_local_datetime(detail.get("dateBeg"))
        closes = _parse_local_datetime(detail.get("dateEnd"))
        normalized_status = _normalized_status(ctx.now, opens, closes)

        percent_bps = (
            _percent_bps(detail.get("percentMaximum"))
            if detail.get("percentMaximumWeb") is True
            else None
        )
        grant_min = (
            _money_minor(detail.get("priceMinimum"))
            if detail.get("priceMinimumWeb") is True
            else None
        )
        grant_max = (
            _money_minor(detail.get("priceMaximum"))
            if detail.get("priceMaximumWeb") is True
            else None
        )
        allocation = (
            _money_minor(detail.get("totalPrice"))
            if detail.get("totalPriceWeb") is True
            else None
        )

        raw_fields = {
            "programCode": code,
            "idDefSubproject": subproject_id,
            "groupCode": item.metadata.get("groupCode"),
            "groupName": item.metadata.get("groupName"),
            "sourceState": item.metadata.get("sourceState"),
            "description": _clean_html(detail.get("desc")),
            "purposeText": _clean_html(detail.get("purposeList")),
            "eligibleApplicantsText": _clean_html(detail.get("applicantsRange")),
            "submissionOpenAtSource": detail.get("dateBeg"),
            "submissionCloseAtSource": detail.get("dateEnd"),
            "submissionOpenAt": opens.isoformat() if opens else None,
            "submissionCloseAt": closes.isoformat() if closes else None,
            "normalizedStatus": normalized_status,
            "supportRateMaxSource": detail.get("percentMaximum"),
            "supportRateMaxBps": percent_bps,
            "grantAmountMinSource": detail.get("priceMinimum"),
            "grantAmountMaxSource": detail.get("priceMaximum"),
            "allocationSource": detail.get("totalPrice"),
            "grantAmountMinMinor": grant_min,
            "grantAmountMaxMinor": grant_max,
            "allocationMinor": allocation,
            "programLinksSource": detail.get("programLinks"),
            "documents": documents,
            "documentCoverage": (
                "METADATA_ONLY_UNTIL_PUBLIC_DOWNLOAD_CONTRACT_VERIFIED"
            ),
            "regionCode": "CZ052",
            "regionName": "Královéhradecký kraj",
            "discoveryMethod": item.metadata.get("discoveryMethod"),
        }

        native = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title=(
                detail.get("name")
                if isinstance(detail.get("name"), str)
                else item.title_hint
            ),
            native_status=(
                f"state:{item.metadata.get('sourceState')}"
                if item.metadata.get("sourceState") is not None
                else None
            ),
            raw_fields=raw_fields,
            artifacts=[],
            snapshot_ids=[
                discovery_snapshot_id,
                detail_snapshot_id,
                documents_snapshot_id,
            ],
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
        # v0.1 intentionally exposes document metadata only. We must not guess
        # a download URL from numeric document IDs. This method becomes active
        # only after the official public download contract is captured.
        raise RuntimeError(
            "KHK document download contract is not yet verified; "
            "artifact fetch is intentionally disabled"
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
                "KHK adapter requires ctx.snapshots for RAW-first ingestion"
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
