from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

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


SEARCH_PATH = "/search-api/prod/rest/search"
SEARCH_BASE = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
PORTAL_TOPIC_BASE = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
    "screen/opportunities/topic-details/"
)

STATUS_FORTHCOMING = "31094501"
STATUS_OPEN = "31094502"
STATUS_CLOSED = "31094503"

_HREF_RE = re.compile(r"""href=["'](https://[^"'<>\s]+)["']""", re.IGNORECASE)
_ALLOWED_ARTIFACT_HOSTS = frozenset({"ec.europa.eu"})


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("metadata")
    return value if isinstance(value, dict) else {}


def _field(record: dict[str, Any], name: str) -> Any:
    if name in record:
        top = record.get(name)
        if top not in (None, ""):
            return _first(top)
    return _first(_metadata(record).get(name))


def _parse_datetime(value: Any) -> datetime | None:
    value = _first(value)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        formats = (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
        )
        parsed = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_object_from_metadata(record: dict[str, Any], name: str) -> Any:
    raw = _first(_metadata(record).get(name))
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _extract_artifacts(record: dict[str, Any]) -> list[RemoteArtifactRef]:
    meta = _metadata(record)
    texts: list[str] = []
    for key in ("topicConditions", "supportInfo", "descriptionByte"):
        raw = _first(meta.get(key))
        if isinstance(raw, str):
            texts.append(raw)

    seen: set[str] = set()
    artifacts: list[RemoteArtifactRef] = []

    for text in texts:
        for match in _HREF_RE.findall(text):
            url = html.unescape(match)
            parsed = urlsplit(url)
            if parsed.hostname not in _ALLOWED_ARTIFACT_HOSTS:
                continue
            if not (
                parsed.path.lower().endswith(".pdf")
                or "/opportunities/docs/" in parsed.path
            ):
                continue
            if url in seen:
                continue
            seen.add(url)

            name = PurePosixPath(parsed.path).name or "document"
            lowered = name.lower()
            role = (
                "CALL_DOCUMENT"
                if "call-fiche" in lowered or "call-document" in lowered
                else "ANNEX"
            )
            external_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
            artifacts.append(
                RemoteArtifactRef(
                    external_id=external_id,
                    url=url,
                    role=role,
                    title=name,
                    mime_hint=(
                        "application/pdf"
                        if parsed.path.lower().endswith(".pdf")
                        else None
                    ),
                )
            )

    return artifacts


def _safe_topic_url(identifier: str, record: dict[str, Any]) -> str:
    candidate = _field(record, "url")
    if isinstance(candidate, str) and candidate.startswith("https://ec.europa.eu/"):
        return candidate
    return PORTAL_TOPIC_BASE + quote(identifier, safe="-_.~")


class EuFundingTendersAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="EU_FT",
        name="EU Funding & Tenders Portal",
        authority=AuthorityLevel.OFFICIAL,
        country_code=None,
        base_url="https://api.tech.ec.europa.eu/",
        retrieval_modes=[RetrievalMode.API, RetrievalMode.JSON],
        allowed_hosts=["api.tech.ec.europa.eu", "ec.europa.eu"],
        allowed_post_paths=[
            "/search-api/prod/rest/search",
            "/search-api/prod/rest/facet",
        ],
        normal_refresh_minutes=240,
        max_concurrency=2,
        requests_per_second=1.0,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    def __init__(self, *, page_size: int = 50) -> None:
        if page_size < 1 or page_size > 200:
            raise ValueError("page_size must be between 1 and 200")
        self.page_size = page_size

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        try:
            payload, _ = await self._search_page(
                ctx,
                page=1,
                page_size=1,
                snapshot=False,
            )
            healthy = isinstance(payload.get("results"), list)
            status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
            detail = None if healthy else "API response has no results array"
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
        page = 1
        if checkpoint and checkpoint.cursor:
            try:
                page = max(1, int(checkpoint.cursor))
            except ValueError as exc:
                raise ValueError("EU_FT checkpoint cursor must be an integer page") from exc

        payload, discovery_snapshot_id = await self._search_page(
            ctx,
            page=page,
            page_size=self.page_size,
            snapshot=True,
        )
        records = payload.get("results")
        if not isinstance(records, list):
            raise ValueError("EU Funding API response has no results list")

        items: list[DiscoveryItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            identifier = _field(record, "identifier")
            if not isinstance(identifier, str) or not identifier:
                continue

            status = _field(record, "status")
            deadline = _parse_datetime(_field(record, "deadlineDate"))
            # SEDIA occasionally carries stale rows still marked open.
            # A past deadline cannot be surfaced as a current open opportunity.
            if (
                status == STATUS_OPEN
                and deadline is not None
                and deadline < ctx.now.astimezone(timezone.utc)
            ):
                continue

            updated_at = _parse_datetime(
                _first(_metadata(record).get("esDA_IngestDate"))
            )
            item_metadata = {
                "reference": record.get("reference"),
                "deadline": deadline.isoformat() if deadline else None,
                "source_status_code": status,
                "source_type_code": _field(record, "type"),
                "framework_programme": _field(record, "frameworkProgramme"),
            }
            if discovery_snapshot_id:
                item_metadata["discovery_snapshot_id"] = discovery_snapshot_id

            items.append(
                DiscoveryItem(
                    external_id=identifier,
                    detail_url=_safe_topic_url(identifier, record),
                    title_hint=_field(record, "title") or record.get("summary"),
                    native_status_hint=status,
                    updated_at_hint=updated_at,
                    metadata=item_metadata,
                )
            )

        try:
            total = int(payload.get("totalResults") or 0)
            response_page_size = int(payload.get("pageSize") or self.page_size)
            response_page = int(payload.get("pageNumber") or page)
        except (TypeError, ValueError):
            total = 0
            response_page_size = self.page_size
            response_page = page

        is_complete = (
            not records
            or total == 0
            or response_page * response_page_size >= total
        )
        next_checkpoint = (
            None
            if is_complete
            else SourceCheckpoint(cursor=str(response_page + 1))
        )

        return DiscoveryPage(
            items=items,
            next_checkpoint=next_checkpoint,
            is_complete=is_complete,
            total_hint=total,
        )

    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        identifier = item.external_id
        query = urlencode(
            {
                "apiKey": "SEDIA",
                "text": f'"{identifier}"',
                "pageSize": "20",
                "pageNumber": "1",
            }
        )
        url = f"{SEARCH_BASE}?{query}"

        headers: dict[str, str] = {}
        if validators:
            if validators.etag:
                headers["if-none-match"] = validators.etag
            if validators.last_modified:
                headers["if-modified-since"] = validators.last_modified

        response = await ctx.http.get(url, headers=headers)
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
            raise RuntimeError(
                f"EU Funding topic detail returned HTTP {response.status_code}"
            )

        payload = json.loads(response.text)
        records = payload.get("results")
        if not isinstance(records, list):
            raise ValueError("EU Funding topic detail response has no results list")

        matched: dict[str, Any] | None = None
        for record in records:
            if (
                isinstance(record, dict)
                and _field(record, "identifier") == identifier
            ):
                matched = record
                break

        if matched is None:
            return RecordFetchResult(
                state=FetchState.GONE,
                http_status=response.status_code,
            )

        snapshot_id = self._snapshot(
            ctx,
            source_url=url,
            content=response.content,
            mime_type=response.headers.get(
                "content-type",
                "application/json",
            ).split(";", 1)[0],
            headers=response.headers,
        )

        meta = _metadata(matched)
        record = NativeRecord(
            source_code=self.descriptor.code,
            external_id=identifier,
            detail_url=_safe_topic_url(identifier, matched),
            native_title=_field(matched, "title") or matched.get("summary"),
            native_status=_field(matched, "status"),
            updated_at=_parse_datetime(_first(meta.get("esDA_IngestDate"))),
            raw_fields={
                "reference": matched.get("reference"),
                "summary": matched.get("summary"),
                "url": matched.get("url"),
                "metadata": meta,
                "budgetOverviewParsed": _json_object_from_metadata(
                    matched,
                    "budgetOverview",
                ),
            },
            artifacts=_extract_artifacts(matched),
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
                f"EU Funding artifact returned HTTP {response.status_code}"
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

    async def _search_page(
        self,
        ctx: AdapterContext,
        *,
        page: int,
        page_size: int,
        snapshot: bool,
    ) -> tuple[dict[str, Any], str | None]:
        query_string = urlencode(
            {
                "apiKey": "SEDIA",
                "text": "***",
                "pageSize": str(page_size),
                "pageNumber": str(page),
            }
        )
        url = f"{SEARCH_BASE}?{query_string}"
        query = {
            "bool": {
                "must": [
                    {"terms": {"type": ["1", "8"]}},
                    {
                        "terms": {
                            "status": [
                                STATUS_FORTHCOMING,
                                STATUS_OPEN,
                            ]
                        }
                    },
                    {"term": {"programmePeriod": "2021 - 2027"}},
                ]
            }
        }
        response = await ctx.http.post_multipart(
            url,
            json_parts={
                "query": query,
                "languages": ["en"],
                "sort": {"field": "sortStatus", "order": "ASC"},
            },
            text_parts={"displayLanguage": "en"},
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"EU Funding search returned HTTP {response.status_code}"
            )
        payload = json.loads(response.text)

        snapshot_id = None
        if snapshot and ctx.snapshots is not None:
            snapshot_id = self._snapshot(
                ctx,
                source_url=url,
                content=response.content,
                mime_type=response.headers.get(
                    "content-type",
                    "application/json",
                ).split(";", 1)[0],
                headers=response.headers,
            )
        return payload, snapshot_id

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
                "EU Funding adapter requires ctx.snapshots for RAW-first ingestion"
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
