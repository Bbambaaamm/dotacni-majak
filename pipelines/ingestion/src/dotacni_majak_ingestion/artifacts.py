from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable

from dotacni_majak_source_sdk import (
    AdapterContext,
    FetchState,
    FetchValidators,
    NativeRecord,
    RemoteArtifactRef,
    SourceAdapter,
)


class ArtifactDownloadError(RuntimeError):
    pass


class ArtifactInvariantError(ArtifactDownloadError):
    pass


class ArtifactMimeRejected(ArtifactDownloadError):
    pass


class ArtifactObservedState(str, Enum):
    MODIFIED = "MODIFIED"
    REUSED = "REUSED"
    GONE = "GONE"


@dataclass(frozen=True, slots=True)
class ArtifactCacheEntry:
    source_code: str
    external_id: str
    url: str
    snapshot_id: str
    sha256: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    artifact: RemoteArtifactRef
    state: ArtifactObservedState
    snapshot_id: str | None
    sha256: str | None
    mime_type: str | None
    size_bytes: int | None
    previous_snapshot_id: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactDownloadPolicy:
    allowed_mime_types: frozenset[str] = frozenset(
        {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/html",
            "text/plain",
            "application/zip",
            "application/octet-stream",
        }
    )
    reject_unknown_mime: bool = False

    def validate_mime(self, mime_type: str | None) -> None:
        if mime_type is None:
            if self.reject_unknown_mime:
                raise ArtifactMimeRejected("artifact MIME type is unknown")
            return
        normalized = mime_type.split(";", 1)[0].strip().lower()
        if normalized not in self.allowed_mime_types:
            raise ArtifactMimeRejected(
                f"artifact MIME type {normalized!r} is not allowed"
            )


class ArtifactCacheRepository(ABC):
    @abstractmethod
    def get(
        self,
        source_code: str,
        artifact: RemoteArtifactRef,
    ) -> ArtifactCacheEntry | None:
        raise NotImplementedError

    @abstractmethod
    def put(self, entry: ArtifactCacheEntry) -> None:
        raise NotImplementedError


class InMemoryArtifactCacheRepository(ArtifactCacheRepository):
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], ArtifactCacheEntry] = {}

    @staticmethod
    def _key(
        source_code: str,
        artifact: RemoteArtifactRef,
    ) -> tuple[str, str, str]:
        return source_code, artifact.external_id, str(artifact.url)

    def get(
        self,
        source_code: str,
        artifact: RemoteArtifactRef,
    ) -> ArtifactCacheEntry | None:
        return self._entries.get(self._key(source_code, artifact))

    def put(self, entry: ArtifactCacheEntry) -> None:
        key = (entry.source_code, entry.external_id, entry.url)
        self._entries[key] = entry


class ArtifactDownloader:
    """Shared conditional downloader for connector artifacts.

    The adapter still owns the actual HTTP request and RAW snapshot creation.
    This layer owns validator reuse and the invariant that HTTP 304 can only be
    accepted when an auditable previous snapshot exists.
    """

    def __init__(
        self,
        *,
        cache: ArtifactCacheRepository,
        policy: ArtifactDownloadPolicy | None = None,
    ) -> None:
        self.cache = cache
        self.policy = policy or ArtifactDownloadPolicy()

    async def download_record_artifacts(
        self,
        *,
        adapter: SourceAdapter,
        ctx: AdapterContext,
        record: NativeRecord,
    ) -> tuple[DownloadedArtifact, ...]:
        downloaded: list[DownloadedArtifact] = []
        for artifact in record.artifacts:
            downloaded.append(
                await self.download(
                    adapter=adapter,
                    ctx=ctx,
                    artifact=artifact,
                )
            )
        return tuple(downloaded)

    async def download(
        self,
        *,
        adapter: SourceAdapter,
        ctx: AdapterContext,
        artifact: RemoteArtifactRef,
    ) -> DownloadedArtifact:
        source_code = adapter.descriptor.code
        cached = self.cache.get(source_code, artifact)
        validators = None
        if cached is not None:
            validators = FetchValidators(
                etag=cached.etag,
                last_modified=cached.last_modified,
                known_sha256=cached.sha256,
            )

        result = await adapter.fetch_artifact(
            ctx,
            artifact,
            validators,
        )

        if result.state == FetchState.NOT_MODIFIED:
            if cached is None or not cached.snapshot_id:
                raise ArtifactInvariantError(
                    "artifact returned NOT_MODIFIED without cached RAW snapshot"
                )
            return DownloadedArtifact(
                artifact=artifact,
                state=ArtifactObservedState.REUSED,
                snapshot_id=cached.snapshot_id,
                sha256=cached.sha256,
                mime_type=cached.mime_type,
                size_bytes=cached.size_bytes,
                previous_snapshot_id=cached.snapshot_id,
            )

        if result.state == FetchState.GONE:
            return DownloadedArtifact(
                artifact=artifact,
                state=ArtifactObservedState.GONE,
                snapshot_id=None,
                sha256=None,
                mime_type=None,
                size_bytes=None,
                previous_snapshot_id=(cached.snapshot_id if cached else None),
            )

        if result.snapshot_id is None:
            raise ArtifactInvariantError(
                "MODIFIED artifact must return a RAW snapshot_id"
            )

        self.policy.validate_mime(result.mime_type)
        entry = ArtifactCacheEntry(
            source_code=source_code,
            external_id=artifact.external_id,
            url=str(artifact.url),
            snapshot_id=result.snapshot_id,
            sha256=result.sha256,
            mime_type=result.mime_type,
            size_bytes=result.size_bytes,
            etag=result.etag,
            last_modified=result.last_modified,
        )
        self.cache.put(entry)

        return DownloadedArtifact(
            artifact=artifact,
            state=ArtifactObservedState.MODIFIED,
            snapshot_id=entry.snapshot_id,
            sha256=entry.sha256,
            mime_type=entry.mime_type,
            size_bytes=entry.size_bytes,
            previous_snapshot_id=(cached.snapshot_id if cached else None),
        )
