from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


_SOURCE_CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    snapshot_id: str
    source_code: str
    source_url: str
    retrieved_at: str
    mime_type: str
    size_bytes: int
    sha256: str
    object_key: str
    etag: str | None = None
    last_modified: str | None = None


class RawSnapshotStore(ABC):
    @abstractmethod
    def put(
        self,
        *,
        source_code: str,
        source_url: str,
        content: bytes,
        mime_type: str,
        retrieved_at: datetime | None = None,
        validators: Mapping[str, str] | None = None,
    ) -> RawSnapshot:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, snapshot: RawSnapshot) -> bytes:
        raise NotImplementedError


class LocalRawSnapshotStore(RawSnapshotStore):
    """Content-addressed local backend used by tests and local development.

    Production storage (R2) must preserve the same immutable object-key and
    metadata semantics through another RawSnapshotStore implementation.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(
        self,
        *,
        source_code: str,
        source_url: str,
        content: bytes,
        mime_type: str,
        retrieved_at: datetime | None = None,
        validators: Mapping[str, str] | None = None,
    ) -> RawSnapshot:
        self._validate_source_code(source_code)
        if not source_url:
            raise ValueError("source_url must not be empty")
        if not mime_type:
            raise ValueError("mime_type must not be empty")

        digest = hashlib.sha256(content).hexdigest()
        captured = retrieved_at or datetime.now(timezone.utc)
        if captured.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")

        object_key = self._object_key(source_code, digest)
        object_path = self.root / object_key
        metadata_path = object_path.with_suffix(object_path.suffix + ".json")

        object_path.parent.mkdir(parents=True, exist_ok=True)

        if object_path.exists():
            existing = object_path.read_bytes()
            existing_digest = hashlib.sha256(existing).hexdigest()
            if existing_digest != digest:
                raise RuntimeError(
                    f"immutable snapshot collision at {object_key}: "
                    f"expected {digest}, found {existing_digest}"
                )
        else:
            object_path.write_bytes(content)

        validators = dict(validators or {})
        url_digest = self._url_digest(source_url)
        snapshot = RawSnapshot(
            snapshot_id=f"{source_code}:{url_digest}:{digest}",
            source_code=source_code,
            source_url=source_url,
            retrieved_at=captured.astimezone(timezone.utc).isoformat(),
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=digest,
            object_key=object_key,
            etag=validators.get("etag"),
            last_modified=validators.get("last_modified"),
        )

        # Keep the legacy content-identity sidecar for compatibility, while also
        # preserving record-specific URL provenance when identical bytes appear at
        # multiple official URLs.
        serialized = json.dumps(
            asdict(snapshot), ensure_ascii=False, indent=2, sort_keys=True
        )
        if not metadata_path.exists():
            metadata_path.write_text(serialized, encoding="utf-8")
        url_metadata_path = self._url_metadata_path(object_path, source_url)
        if not url_metadata_path.exists():
            url_metadata_path.write_text(serialized, encoding="utf-8")

        return snapshot

    def get_bytes(self, snapshot: RawSnapshot) -> bytes:
        content = (self.root / snapshot.object_key).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != snapshot.sha256:
            raise RuntimeError(
                f"snapshot integrity check failed for {snapshot.object_key}"
            )
        return content

    def load_by_sha256(
        self,
        *,
        source_code: str,
        sha256: str,
        source_url: str | None = None,
    ) -> RawSnapshot:
        """Load one immutable RAW object with optional URL-specific provenance."""
        self._validate_source_code(source_code)
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError("sha256 must be lowercase 64-character hex")
        object_key = self._object_key(source_code, sha256)
        object_path = self.root / object_key
        legacy_path = object_path.with_suffix(".bin.json")
        if source_url is None:
            aliases = sorted(
                object_path.parent.glob(object_path.name + ".url-*.json")
            )
            if len(aliases) > 1:
                raise RuntimeError(
                    "RAW snapshot provenance is ambiguous; source_url is required"
                )
            metadata_path = aliases[0] if aliases else legacy_path
        else:
            metadata_path = self._url_metadata_path(object_path, source_url)
            if not metadata_path.exists() and legacy_path.exists():
                legacy = RawSnapshot(
                    **json.loads(legacy_path.read_text(encoding="utf-8"))
                )
                if legacy.source_url == source_url:
                    metadata_path = legacy_path
        if not metadata_path.exists():
            suffix = f" at {source_url}" if source_url is not None else ""
            raise FileNotFoundError(
                f"RAW snapshot metadata not found for {source_code}:{sha256}{suffix}"
            )
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        snapshot = RawSnapshot(**raw)
        if snapshot.source_code != source_code or snapshot.sha256 != sha256:
            raise RuntimeError("RAW snapshot metadata identity mismatch")
        if source_url is not None and snapshot.source_url != source_url:
            raise RuntimeError("RAW snapshot URL provenance mismatch")
        self.get_bytes(snapshot)
        return snapshot

    @staticmethod
    def _validate_source_code(source_code: str) -> None:
        if not _SOURCE_CODE_RE.fullmatch(source_code):
            raise ValueError(
                "source_code must contain only letters, digits, underscore or hyphen"
            )

    def load_by_snapshot_id(self, snapshot_id: str) -> RawSnapshot:
        parts = snapshot_id.split(":")
        if len(parts) == 2:
            source_code, digest = parts
            return self.load_by_sha256(
                source_code=source_code,
                sha256=digest,
            )
        if len(parts) != 3:
            raise ValueError("snapshot_id must be source:url-digest:sha256")
        source_code, url_digest, digest = parts
        self._validate_source_code(source_code)
        if not re.fullmatch(r"[0-9a-f]{24}", url_digest):
            raise ValueError("snapshot_id URL digest is invalid")
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("snapshot_id SHA-256 is invalid")
        object_path = self.root / self._object_key(source_code, digest)
        metadata_path = object_path.with_name(
            object_path.name + f".url-{url_digest}.json"
        )
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"RAW snapshot metadata not found for {snapshot_id}"
            )
        snapshot = RawSnapshot(
            **json.loads(metadata_path.read_text(encoding="utf-8"))
        )
        if (
            snapshot.source_code != source_code
            or snapshot.sha256 != digest
            or self._url_digest(snapshot.source_url) != url_digest
        ):
            raise RuntimeError("RAW snapshot metadata identity mismatch")
        self.get_bytes(snapshot)
        return snapshot

    @staticmethod
    def _url_digest(source_url: str) -> str:
        return hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def _url_metadata_path(cls, object_path: Path, source_url: str) -> Path:
        url_digest = cls._url_digest(source_url)
        return object_path.with_name(object_path.name + f".url-{url_digest}.json")

    @staticmethod
    def _object_key(source_code: str, digest: str) -> str:
        return f"raw/{source_code}/{digest[:2]}/{digest[2:4]}/{digest}.bin"
