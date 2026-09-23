from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol
from uuid import uuid4


_TOKEN_DOMAIN = b"dotacni-majak-project-owner-v1\x00"


class OwnerAuditEventType(str, Enum):
    CREATED = "CREATED"
    VERIFIED = "VERIFIED"
    ROTATED = "ROTATED"
    REVOKED = "REVOKED"
    DENIED_UNKNOWN = "DENIED_UNKNOWN"
    DENIED_REVOKED = "DENIED_REVOKED"
    DENIED_PROJECT_MISMATCH = "DENIED_PROJECT_MISMATCH"


@dataclass(frozen=True, slots=True)
class ProjectOwnerCapability:
    project_id: str
    token_hash: str
    generation: int
    created_at: datetime
    rotated_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IssuedOwnerCapability:
    capability: ProjectOwnerCapability
    token: str


@dataclass(frozen=True, slots=True)
class OwnerAuditEvent:
    id: str
    project_id: str | None
    event_type: OwnerAuditEventType
    created_at: datetime


class ProjectAccessRepository(Protocol):
    def create(self, capability: ProjectOwnerCapability) -> ProjectOwnerCapability: ...
    def get(self, project_id: str) -> ProjectOwnerCapability | None: ...
    def find_by_hash(self, token_hash: str) -> ProjectOwnerCapability | None: ...
    def save(self, capability: ProjectOwnerCapability) -> ProjectOwnerCapability: ...
    def append_audit(self, event: OwnerAuditEvent) -> None: ...


class InMemoryProjectAccessRepository:
    def __init__(self) -> None:
        self.capabilities: dict[str, ProjectOwnerCapability] = {}
        self.by_hash: dict[str, str] = {}
        self.audit: list[OwnerAuditEvent] = []

    def create(self, capability: ProjectOwnerCapability) -> ProjectOwnerCapability:
        if capability.project_id in self.capabilities:
            raise ValueError("project already has an owner capability")
        if capability.token_hash in self.by_hash:
            raise ValueError("duplicate owner capability hash")
        self.capabilities[capability.project_id] = capability
        self.by_hash[capability.token_hash] = capability.project_id
        return capability

    def get(self, project_id: str) -> ProjectOwnerCapability | None:
        return self.capabilities.get(project_id)

    def find_by_hash(self, token_hash: str) -> ProjectOwnerCapability | None:
        project_id = self.by_hash.get(token_hash)
        return self.capabilities.get(project_id) if project_id else None

    def save(self, capability: ProjectOwnerCapability) -> ProjectOwnerCapability:
        previous = self.capabilities.get(capability.project_id)
        if previous is None:
            raise KeyError(capability.project_id)
        if previous.token_hash != capability.token_hash:
            self.by_hash.pop(previous.token_hash, None)
            if capability.token_hash in self.by_hash:
                raise ValueError("duplicate owner capability hash")
            self.by_hash[capability.token_hash] = capability.project_id
        self.capabilities[capability.project_id] = capability
        return capability

    def append_audit(self, event: OwnerAuditEvent) -> None:
        self.audit.append(event)


class ProjectOwnerCapabilityService:
    def __init__(
        self,
        repository: ProjectAccessRepository,
        *,
        token_bytes: int = 32,
    ) -> None:
        if token_bytes < 32:
            raise ValueError("token_bytes must provide at least 256 bits")
        self.repository = repository
        self.token_bytes = token_bytes

    def issue(
        self,
        project_id: str,
        *,
        now: datetime | None = None,
    ) -> IssuedOwnerCapability:
        current = _utc(now)
        token = secrets.token_urlsafe(self.token_bytes)
        capability = ProjectOwnerCapability(
            project_id=project_id,
            token_hash=_hash_token(token),
            generation=1,
            created_at=current,
        )
        created = self.repository.create(capability)
        self._audit(project_id, OwnerAuditEventType.CREATED, current)
        return IssuedOwnerCapability(created, token)

    def verify(
        self,
        project_id: str,
        token: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now)
        if not _valid_token_shape(token):
            self._audit(None, OwnerAuditEventType.DENIED_UNKNOWN, current)
            return False
        capability = self.repository.find_by_hash(_hash_token(token))
        if capability is None:
            self._audit(None, OwnerAuditEventType.DENIED_UNKNOWN, current)
            return False
        if capability.project_id != project_id:
            self._audit(project_id, OwnerAuditEventType.DENIED_PROJECT_MISMATCH, current)
            return False
        if capability.revoked_at is not None:
            self._audit(project_id, OwnerAuditEventType.DENIED_REVOKED, current)
            return False
        self.repository.save(replace(capability, last_used_at=current))
        self._audit(project_id, OwnerAuditEventType.VERIFIED, current)
        return True

    def rotate(
        self,
        project_id: str,
        token: str,
        *,
        now: datetime | None = None,
    ) -> IssuedOwnerCapability:
        current = _utc(now)
        if not self.verify(project_id, token, now=current):
            raise PermissionError("invalid project owner capability")
        capability = self.repository.get(project_id)
        if capability is None:
            raise PermissionError("invalid project owner capability")
        new_token = secrets.token_urlsafe(self.token_bytes)
        rotated = replace(
            capability,
            token_hash=_hash_token(new_token),
            generation=capability.generation + 1,
            rotated_at=current,
            last_used_at=current,
        )
        saved = self.repository.save(rotated)
        self._audit(project_id, OwnerAuditEventType.ROTATED, current)
        return IssuedOwnerCapability(saved, new_token)

    def revoke(
        self,
        project_id: str,
        token: str,
        *,
        now: datetime | None = None,
    ) -> ProjectOwnerCapability:
        current = _utc(now)
        if not self.verify(project_id, token, now=current):
            raise PermissionError("invalid project owner capability")
        capability = self.repository.get(project_id)
        if capability is None:
            raise PermissionError("invalid project owner capability")
        revoked = self.repository.save(replace(capability, revoked_at=current))
        self._audit(project_id, OwnerAuditEventType.REVOKED, current)
        return revoked

    def _audit(
        self,
        project_id: str | None,
        event_type: OwnerAuditEventType,
        now: datetime,
    ) -> None:
        self.repository.append_audit(
            OwnerAuditEvent(
                id=f"poc_{uuid4().hex}",
                project_id=project_id,
                event_type=event_type,
                created_at=now,
            )
        )


def _hash_token(token: str) -> str:
    return hashlib.sha256(_TOKEN_DOMAIN + token.encode("utf-8")).hexdigest()


def _valid_token_shape(token: str) -> bool:
    return 40 <= len(token) <= 128 and all(
        ch.isalnum() or ch in "-_" for ch in token
    )


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)
