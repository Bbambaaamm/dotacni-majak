from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit

from .adapter import AdapterContext, SourceAdapter
from .http import GuardedResponse
from .models import FetchState, HealthStatus, SourceCheckpoint


@dataclass(frozen=True, slots=True)
class FixtureRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    json_parts: Mapping[str, Any] | None = None
    text_parts: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class FixtureResponse:
    status_code: int = 200
    headers: Mapping[str, str] | None = None
    content: bytes = b""


class FixtureHttpClient:
    """Deterministic no-network HTTP double for connector contract tests.

    Routes are exact method+URL matches. Each route may contain multiple
    responses; repeated calls consume responses in order and the final
    response is reused once only one remains.
    """

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], list[FixtureResponse]] = {}
        self.requests: list[FixtureRequest] = []

    def add(
        self,
        method: str,
        url: str,
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        content: bytes | str = b"",
    ) -> None:
        payload = content.encode("utf-8") if isinstance(content, str) else content
        self._routes.setdefault((method.upper(), url), []).append(
            FixtureResponse(
                status_code=status_code,
                headers=dict(headers or {}),
                content=payload,
            )
        )

    def _response(self, method: str, url: str) -> GuardedResponse:
        key = (method.upper(), url)
        responses = self._routes.get(key)
        if not responses:
            raise AssertionError(f"unexpected fixture HTTP request: {method} {url}")
        response = responses[0]
        if len(responses) > 1:
            responses.pop(0)
        return GuardedResponse(
            status_code=response.status_code,
            headers=dict(response.headers or {}),
            content=response.content,
            url=url,
        )

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        max_response_bytes: int | None = None,
    ) -> GuardedResponse:
        del max_response_bytes
        self.requests.append(
            FixtureRequest("GET", url, dict(headers or {}))
        )
        return self._response("GET", url)

    async def post_multipart(
        self,
        url: str,
        *,
        json_parts: Mapping[str, Any],
        text_parts: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        max_response_bytes: int | None = None,
    ) -> GuardedResponse:
        del max_response_bytes
        self.requests.append(
            FixtureRequest(
                "POST",
                url,
                dict(headers or {}),
                dict(json_parts),
                dict(text_parts or {}),
            )
        )
        return self._response("POST", url)


@dataclass(frozen=True, slots=True)
class FixtureSnapshot:
    snapshot_id: str
    sha256: str
    size_bytes: int


class FixtureSnapshotStore:
    """Minimal RAW store double matching the adapter-facing .put contract."""

    def __init__(self) -> None:
        self.snapshots: dict[str, bytes] = {}
        self.put_calls: list[dict[str, Any]] = []

    def put(
        self,
        *,
        source_code: str,
        source_url: str,
        content: bytes,
        mime_type: str,
        retrieved_at: datetime | None = None,
        validators: Mapping[str, str] | None = None,
    ) -> FixtureSnapshot:
        digest = hashlib.sha256(content).hexdigest()
        snapshot_id = f"{source_code}:{digest}"
        self.snapshots[snapshot_id] = bytes(content)
        self.put_calls.append(
            {
                "source_code": source_code,
                "source_url": source_url,
                "mime_type": mime_type,
                "retrieved_at": retrieved_at,
                "validators": dict(validators or {}),
                "snapshot_id": snapshot_id,
            }
        )
        return FixtureSnapshot(
            snapshot_id=snapshot_id,
            sha256=digest,
            size_bytes=len(content),
        )


@dataclass(frozen=True, slots=True)
class AdapterContractReport:
    source_code: str
    health_status: HealthStatus
    discovered: int
    first_record_state: FetchState | None
    snapshots_created: int


def make_fixture_context(
    *,
    http: FixtureHttpClient,
    snapshots: FixtureSnapshotStore | None = None,
    run_id: str = "contract-test",
    now: datetime | None = None,
) -> AdapterContext:
    return AdapterContext(
        run_id=run_id,
        http=http,
        logger=None,
        budget=None,
        snapshots=snapshots or FixtureSnapshotStore(),
        now=now or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def assert_descriptor_contract(adapter: SourceAdapter) -> None:
    descriptor = adapter.descriptor
    if not re.fullmatch(r"[A-Z0-9_]+", descriptor.code):
        raise AssertionError(
            f"source code must be stable uppercase token, got {descriptor.code!r}"
        )
    if not descriptor.name.strip():
        raise AssertionError("source name must not be empty")
    if not descriptor.adapter_version.strip():
        raise AssertionError("adapter_version must not be empty")
    if not descriptor.retrieval_modes:
        raise AssertionError("retrieval_modes must not be empty")

    base = urlsplit(str(descriptor.base_url))
    if base.scheme != "https" or not base.hostname:
        raise AssertionError("base_url must be an absolute HTTPS URL")

    allowed = {host.rstrip(".").lower() for host in descriptor.allowed_hosts}
    if base.hostname.rstrip(".").lower() not in allowed:
        raise AssertionError("base_url hostname must be included in allowed_hosts")
    if len(allowed) != len(descriptor.allowed_hosts):
        raise AssertionError("allowed_hosts must not contain duplicates")

    for path in descriptor.allowed_post_paths:
        if not path.startswith("/") or "?" in path or "#" in path:
            raise AssertionError(
                f"invalid allowed_post_path {path!r}; use path without query/fragment"
            )


def assert_discovery_page_contract(
    adapter: SourceAdapter,
    page: Any,
) -> None:
    ids = [item.external_id for item in page.items]
    if len(ids) != len(set(ids)):
        raise AssertionError("discovery page contains duplicate external_id values")
    if any(not external_id.strip() for external_id in ids):
        raise AssertionError("discovery external_id must not be empty")
    if not page.is_complete and page.next_checkpoint is None:
        raise AssertionError(
            "incomplete discovery page must provide next_checkpoint"
        )
    if page.total_hint is not None and page.total_hint < len(page.items):
        raise AssertionError("total_hint cannot be smaller than page item count")

    allowed = {
        host.rstrip(".").lower()
        for host in adapter.descriptor.allowed_hosts
    }
    for item in page.items:
        parsed = urlsplit(str(item.detail_url))
        if parsed.scheme != "https" or not parsed.hostname:
            raise AssertionError("detail_url must be absolute HTTPS")
        if parsed.hostname.rstrip(".").lower() not in allowed:
            raise AssertionError(
                f"detail_url host {parsed.hostname!r} is not allowlisted"
            )


def assert_record_contract(
    adapter: SourceAdapter,
    item: Any,
    result: Any,
) -> None:
    if result.state == FetchState.MODIFIED:
        if result.record is None:
            raise AssertionError("MODIFIED record result must contain record")
        record = result.record
        if record.source_code != adapter.descriptor.code:
            raise AssertionError(
                "record.source_code must match adapter descriptor code"
            )
        if record.external_id != item.external_id:
            raise AssertionError(
                "record.external_id must match discovery item external_id"
            )
        if not record.snapshot_ids:
            raise AssertionError(
                "MODIFIED record must reference at least one RAW snapshot"
            )

        artifact_ids = [artifact.external_id for artifact in record.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise AssertionError(
                "record artifacts must have unique external_id values"
            )
        allowed = {
            host.rstrip(".").lower()
            for host in adapter.descriptor.allowed_hosts
        }
        for artifact in record.artifacts:
            parsed = urlsplit(str(artifact.url))
            if parsed.scheme != "https" or not parsed.hostname:
                raise AssertionError("artifact URL must be absolute HTTPS")
            if parsed.hostname.rstrip(".").lower() not in allowed:
                raise AssertionError(
                    f"artifact host {parsed.hostname!r} is not allowlisted"
                )
    elif result.state == FetchState.NOT_MODIFIED:
        raise AssertionError(
            "initial contract fetch without validators must not return NOT_MODIFIED"
        )


async def exercise_adapter_contract(
    adapter: SourceAdapter,
    ctx: AdapterContext,
    *,
    require_items: bool = True,
) -> AdapterContractReport:
    assert_descriptor_contract(adapter)

    health = await adapter.healthcheck(ctx)
    if health.status == HealthStatus.UNAVAILABLE:
        raise AssertionError(
            f"fixture contract healthcheck is unavailable: {health.detail}"
        )

    page = await adapter.discover(ctx, SourceCheckpoint())
    assert_discovery_page_contract(adapter, page)

    first_state: FetchState | None = None
    if page.items:
        result = await adapter.fetch_record(ctx, page.items[0], None)
        assert_record_contract(adapter, page.items[0], result)
        first_state = result.state
    elif require_items:
        raise AssertionError("fixture contract discovery returned zero records")

    snapshots = getattr(ctx.snapshots, "snapshots", {})
    return AdapterContractReport(
        source_code=adapter.descriptor.code,
        health_status=health.status,
        discovered=len(page.items),
        first_record_state=first_state,
        snapshots_created=len(snapshots),
    )
