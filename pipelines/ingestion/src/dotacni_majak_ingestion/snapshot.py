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
        snapshot = RawSnapshot(
            snapshot_id=f"{source_code}:{digest}",
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

        # Metadata is append-safe by content identity. Repeated discovery of the
        # same bytes must never mutate the immutable content object.
        if not metadata_path.exists():
            metadata_path.write_text(
                json.dumps(asdict(snapshot), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )

        return snapshot

    def get_bytes(self, snapshot: RawSnapshot) -> bytes:
        content = (self.root / snapshot.object_key).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != snapshot.sha256:
            raise RuntimeError(
                f"snapshot integrity check failed for {snapshot.object_key}"
            )
        return content

    def load_by_sha256(self, *, source_code: str, sha256: str) -> RawSnapshot:
        """Load and integrity-check one content-addressed local RAW snapshot."""
        self._validate_source_code(source_code)
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError("sha256 must be lowercase 64-character hex")
        object_key = self._object_key(source_code, sha256)
        metadata_path = (self.root / object_key).with_suffix(".bin.json")
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"RAW snapshot metadata not found for {source_code}:{sha256}"
            )
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        snapshot = RawSnapshot(**raw)
        if snapshot.source_code != source_code or snapshot.sha256 != sha256:
            raise RuntimeError("RAW snapshot metadata identity mismatch")
        self.get_bytes(snapshot)
        return snapshot

    @staticmethod
    def _validate_source_code(source_code: str) -> None:
        if not _SOURCE_CODE_RE.fullmatch(source_code):
            raise ValueError(
                "source_code must contain only letters, digits, underscore or hyphen"
            )

    @staticmethod
    def _object_key(source_code: str, digest: str) -> str:
        return f"raw/{source_code}/{digest[:2]}/{digest[2:4]}/{digest}.bin"
