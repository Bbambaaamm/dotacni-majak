from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol
from uuid import uuid4


_TOKEN_DOMAIN = b"dotacni-majak-project-share-v1\x00"


class ShareScope(str, Enum):
    PROJECT_READ_ONLY = "PROJECT_READ_ONLY"


class ShareAuditEventType(str, Enum):
    CREATED = "CREATED"
    RESOLVED = "RESOLVED"
    REVOKED = "REVOKED"
    DENIED_OWNER_MISMATCH = "DENIED_OWNER_MISMATCH"
    DENIED_REVOKED = "DENIED_REVOKED"
    DENIED_EXPIRED = "DENIED_EXPIRED"
    DENIED_UNKNOWN_TOKEN = "DENIED_UNKNOWN_TOKEN"


class ShareResolutionStatus(str, Enum):
    GRANTED = "GRANTED"
    NOT_FOUND = "NOT_FOUND"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ProjectShareLink:
    id: str
    project_id: str
    owner_user_id: str
    token_hash: str
    scope: ShareScope
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None = None
    last_accessed_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class IssuedProjectShare:
    link: ProjectShareLink
    token: str

    @property
    def url_path(self) -> str:
        return f"/s/{self.token}"


@dataclass(frozen=True, slots=True)
class ShareResolution:
    status: ShareResolutionStatus
    project_id: str | None = None
    share_link_id: str | None = None
    scope: ShareScope | None = None

    @property
    def granted(self) -> bool:
        return self.status is ShareResolutionStatus.GRANTED


@dataclass(frozen=True, slots=True)
class ShareAuditEvent:
    id: str
    share_link_id: str | None
    project_id: str | None
    actor_user_id: str | None
    event_type: ShareAuditEventType
    created_at: datetime


class SharingRepository(Protocol):
    def project_owner(self, project_id: str) -> str | None: ...
    def create_share(self, link: ProjectShareLink) -> ProjectShareLink: ...
    def get_share(self, share_link_id: str) -> ProjectShareLink | None: ...
    def find_by_token_hash(self, token_hash: str) -> ProjectShareLink | None: ...
    def save_share(self, link: ProjectShareLink) -> ProjectShareLink: ...
    def append_audit(self, event: ShareAuditEvent) -> None: ...


class InMemorySharingRepository:
    def __init__(self, *, project_owners: dict[str, str] | None = None) -> None:
        self.project_owners = dict(project_owners or {})
        self.links: dict[str, ProjectShareLink] = {}
        self.by_token_hash: dict[str, str] = {}
        self.audit: list[ShareAuditEvent] = []

    def project_owner(self, project_id: str) -> str | None:
        return self.project_owners.get(project_id)

    def create_share(self, link: ProjectShareLink) -> ProjectShareLink:
        if link.token_hash in self.by_token_hash:
            raise ValueError("duplicate share token hash")
        self.links[link.id] = link
        self.by_token_hash[link.token_hash] = link.id
        return link

    def get_share(self, share_link_id: str) -> ProjectShareLink | None:
        return self.links.get(share_link_id)

    def find_by_token_hash(self, token_hash: str) -> ProjectShareLink | None:
        link_id = self.by_token_hash.get(token_hash)
        return self.links.get(link_id) if link_id else None

    def save_share(self, link: ProjectShareLink) -> ProjectShareLink:
        if link.id not in self.links:
            raise KeyError(link.id)
        self.links[link.id] = link
        return link

    def append_audit(self, event: ShareAuditEvent) -> None:
        self.audit.append(event)


class ProjectSharingService:
    """Issues revocable read-only capability links.

    Raw tokens are returned only once and are never stored by the service.
    Repository persistence stores only SHA-256 token hashes.
    """

    def __init__(
        self,
        repository: SharingRepository,
        *,
        default_ttl: timedelta = timedelta(days=30),
        max_ttl: timedelta = timedelta(days=365),
        token_bytes: int = 32,
    ) -> None:
        if default_ttl <= timedelta(0):
            raise ValueError("default_ttl must be positive")
        if max_ttl < default_ttl:
            raise ValueError("max_ttl must be >= default_ttl")
        if token_bytes < 32:
            raise ValueError("token_bytes must provide at least 256 bits")
        self.repository = repository
        self.default_ttl = default_ttl
        self.max_ttl = max_ttl
        self.token_bytes = token_bytes

    def create(
        self,
        *,
        project_id: str,
        owner_user_id: str,
        now: datetime | None = None,
        ttl: timedelta | None = None,
    ) -> IssuedProjectShare:
        current = _utc(now)
        actual_ttl = ttl or self.default_ttl
        if actual_ttl <= timedelta(0) or actual_ttl > self.max_ttl:
            raise ValueError("share ttl is outside allowed bounds")

        owner = self.repository.project_owner(project_id)
        if owner != owner_user_id:
            self._audit(
                ShareAuditEventType.DENIED_OWNER_MISMATCH,
                now=current,
                project_id=project_id,
                actor_user_id=owner_user_id,
            )
            raise PermissionError("project is not owned by caller")

        token = secrets.token_urlsafe(self.token_bytes)
        token_hash = _hash_token(token)
        link = ProjectShareLink(
            id=f"shr_{uuid4().hex}",
            project_id=project_id,
            owner_user_id=owner_user_id,
            token_hash=token_hash,
            scope=ShareScope.PROJECT_READ_ONLY,
            created_at=current,
            expires_at=current + actual_ttl,
        )
        created = self.repository.create_share(link)
        self._audit(
            ShareAuditEventType.CREATED,
            now=current,
            share_link_id=created.id,
            project_id=project_id,
            actor_user_id=owner_user_id,
        )
        return IssuedProjectShare(link=created, token=token)

    def resolve(
        self,
        token: str,
        *,
        now: datetime | None = None,
    ) -> ShareResolution:
        current = _utc(now)
        if not _valid_token_shape(token):
            self._audit(
                ShareAuditEventType.DENIED_UNKNOWN_TOKEN,
                now=current,
            )
            return ShareResolution(status=ShareResolutionStatus.NOT_FOUND)

        link = self.repository.find_by_token_hash(_hash_token(token))
        if link is None:
            self._audit(
                ShareAuditEventType.DENIED_UNKNOWN_TOKEN,
                now=current,
            )
            return ShareResolution(status=ShareResolutionStatus.NOT_FOUND)

        if link.revoked_at is not None:
            self._audit(
                ShareAuditEventType.DENIED_REVOKED,
                now=current,
                share_link_id=link.id,
                project_id=link.project_id,
            )
            return ShareResolution(
                status=ShareResolutionStatus.REVOKED,
                share_link_id=link.id,
            )

        if link.expires_at is not None and current >= link.expires_at:
            self._audit(
                ShareAuditEventType.DENIED_EXPIRED,
                now=current,
                share_link_id=link.id,
                project_id=link.project_id,
            )
            return ShareResolution(
                status=ShareResolutionStatus.EXPIRED,
                share_link_id=link.id,
            )

        self.repository.save_share(replace(link, last_accessed_at=current))
        self._audit(
            ShareAuditEventType.RESOLVED,
            now=current,
            share_link_id=link.id,
            project_id=link.project_id,
        )
        return ShareResolution(
            status=ShareResolutionStatus.GRANTED,
            project_id=link.project_id,
            share_link_id=link.id,
            scope=link.scope,
        )

    def revoke(
        self,
        *,
        share_link_id: str,
        owner_user_id: str,
        now: datetime | None = None,
    ) -> ProjectShareLink:
        current = _utc(now)
        link = self.repository.get_share(share_link_id)
        if link is None:
            raise KeyError(share_link_id)

        if link.owner_user_id != owner_user_id:
            self._audit(
                ShareAuditEventType.DENIED_OWNER_MISMATCH,
                now=current,
                share_link_id=link.id,
                project_id=link.project_id,
                actor_user_id=owner_user_id,
            )
            raise PermissionError("share link is not owned by caller")

        if link.revoked_at is not None:
            return link

        revoked = self.repository.save_share(
            replace(link, revoked_at=current)
        )
        self._audit(
            ShareAuditEventType.REVOKED,
            now=current,
            share_link_id=link.id,
            project_id=link.project_id,
            actor_user_id=owner_user_id,
        )
        return revoked

    def _audit(
        self,
        event_type: ShareAuditEventType,
        *,
        now: datetime,
        share_link_id: str | None = None,
        project_id: str | None = None,
        actor_user_id: str | None = None,
    ) -> None:
        self.repository.append_audit(
            ShareAuditEvent(
                id=f"sha_{uuid4().hex}",
                share_link_id=share_link_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                created_at=now,
            )
        )


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(_TOKEN_DOMAIN + token.encode("utf-8")).hexdigest()


def _valid_token_shape(token: str) -> bool:
    # token_urlsafe(32) is currently 43 chars. Permit a small future range,
    # but reject tiny user-controlled strings before any repository lookup.
    return 40 <= len(token) <= 128 and all(
        ch.isalnum() or ch in "-_" for ch in token
    )
