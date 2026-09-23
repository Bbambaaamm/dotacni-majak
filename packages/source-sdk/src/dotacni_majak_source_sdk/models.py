from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class AuthorityLevel(str, Enum):
    OFFICIAL = "OFFICIAL"
    OFFICIAL_OPEN_DATA = "OFFICIAL_OPEN_DATA"
    SECONDARY = "SECONDARY"


class RetrievalMode(str, Enum):
    API = "API"
    JSON = "JSON"
    XML = "XML"
    RSS = "RSS"
    CSV = "CSV"
    XLSX = "XLSX"
    HTML = "HTML"
    PDF = "PDF"
    DOCX = "DOCX"


class SourceDescriptor(BaseModel):
    code: str
    name: str
    authority: AuthorityLevel
    country_code: str | None = None
    base_url: HttpUrl
    retrieval_modes: list[RetrievalMode]
    allowed_hosts: list[str]
    allowed_post_paths: list[str] = Field(default_factory=list)
    normal_refresh_minutes: int = Field(default=360, ge=1)
    max_concurrency: int = Field(default=2, ge=1)
    requests_per_second: float = Field(default=1.0, gt=0)
    disappearance_confirmation_runs: int = Field(default=3, ge=1)
    adapter_version: str


class SourceCheckpoint(BaseModel):
    cursor: str | None = None
    updated_after: datetime | None = None
    opaque_state: dict[str, Any] = Field(default_factory=dict)


class DiscoveryItem(BaseModel):
    external_id: str
    detail_url: HttpUrl
    title_hint: str | None = None
    native_status_hint: str | None = None
    published_at_hint: datetime | None = None
    updated_at_hint: datetime | None = None
    etag_hint: str | None = None
    last_modified_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoveryPage(BaseModel):
    items: list[DiscoveryItem]
    next_checkpoint: SourceCheckpoint | None = None
    is_complete: bool
    total_hint: int | None = None


ArtifactRole = Literal[
    "CALL_DOCUMENT", "GUIDELINES", "ANNEX", "APPLICATION_FORM",
    "FAQ", "PROGRAMME_DOCUMENT", "OTHER",
]


class RemoteArtifactRef(BaseModel):
    external_id: str
    url: HttpUrl
    role: ArtifactRole
    title: str | None = None
    mime_hint: str | None = None
    required: bool = False


class NativeRecord(BaseModel):
    source_code: str
    external_id: str
    detail_url: HttpUrl
    native_title: str | None = None
    native_status: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    raw_fields: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[RemoteArtifactRef] = Field(default_factory=list)
    snapshot_ids: list[str] = Field(default_factory=list)


class FetchValidators(BaseModel):
    etag: str | None = None
    last_modified: str | None = None
    known_sha256: str | None = None


class FetchState(str, Enum):
    MODIFIED = "MODIFIED"
    NOT_MODIFIED = "NOT_MODIFIED"
    GONE = "GONE"


class RecordFetchResult(BaseModel):
    state: FetchState
    record: NativeRecord | None = None
    http_status: int | None = None
    etag: str | None = None
    last_modified: str | None = None


class ArtifactFetchResult(BaseModel):
    state: FetchState
    snapshot_id: str | None = None
    sha256: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    etag: str | None = None
    last_modified: str | None = None


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class HealthReport(BaseModel):
    status: HealthStatus
    checked_at: datetime
    latency_ms: int | None = None
    detail: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
