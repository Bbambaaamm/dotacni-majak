"""Grounded application drafting assistant — provider interface.

This module defines the domain-layer abstraction for a drafting assistant
that helps users write grant-application text from their project and a
specific grant call — *without* altering official grant conditions.

Design mirrors packages/search/semantic.py: the provider is an optional
Protocol, failures degrade to an explicit unavailable result, and official
facts are always clearly separated from AI-generated content.

See ADR-0008 for the full design rationale.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol
from uuid import uuid4


class DraftSegmentSource(str, Enum):
    """Provenance of a drafted text segment.

    Every segment is ALWAYS explicitly labeled so that official facts
    sourced from the grant call are never confused with AI-generated
    application text.
    """
    OFFICIAL_FACT = "OFFICIAL_FACT"
    AI_DRAFT = "AI_DRAFT"


class DraftingAuditEventType(str, Enum):
    DRAFT_REQUESTED = "DRAFT_REQUESTED"
    DRAFT_COMPLETED = "DRAFT_COMPLETED"
    DRAFT_FAILED = "DRAFT_FAILED"
    DRAFT_UNAVAILABLE = "DRAFT_UNAVAILABLE"
    DRAFT_DENIED = "DRAFT_DENIED"
    PROVIDER_ERROR = "PROVIDER_ERROR"


@dataclass(frozen=True, slots=True)
class OfficialFact:
    """A fact sourced from an official grant-call document.

    ``content`` is official text; ``source_reference`` identifies the
    document and section for provenance display to the user
    (e.g. ``"nsa:detail:v1:eligibility"``).
    """
    content: str
    source_reference: str


@dataclass(frozen=True, slots=True)
class DraftingContext:
    """Prompt/context contract for application drafting.

    Separates OFFICIAL facts (from the grant call — read-only reference)
    from USER-supplied project data (intent, budget, notes).  The provider
    receives this structured context so official grant conditions are only
    *referenced*, never *altered*.

    Per issue #362: *ne měnit dotační podmínky* — draft text is built
    *from* the project and challenge, not by changing official terms.
    """
    project_id: str
    grant_call_id: str
    grant_call_version_id: str
    natural_language_intent: str
    official_facts: tuple[OfficialFact, ...] = ()
    user_notes: str = ""
    max_segments: int = 10

    def __post_init__(self) -> None:
        if not self.grant_call_version_id:
            raise ValueError("grant_call_version_id is required")
        if not self.natural_language_intent.strip():
            raise ValueError("natural_language_intent must not be empty")
        if self.max_segments < 1 or self.max_segments > 100:
            raise ValueError("max_segments must be between 1 and 100")


class DraftingProvider(Protocol):
    """Abstraction over an AI text-generation provider.

    IMPLEMENTATIONS ARE OPTIONAL — ``DraftingAssistant`` degrades to an
    *unavailable* result when no provider is configured (``provider=None``).
    This guarantees **no paid hard dependency** for the core drafting
    workflow (acceptance: *Žádný paywall pro core workflow*).

    Mirrors the ``EmbeddingProvider`` pattern from ``semantic.py``: the
    core package never depends on a specific provider.  A concrete
    connector (e.g. for OpenAI, Claude, or a local model) is a separate,
    independently-enabled adapter.
    """
    @property
    def name(self) -> str: ...

    async def draft(
        self,
        context: DraftingContext,
    ) -> list[DraftedSegment]: ...


@dataclass(frozen=True, slots=True)
class DraftedSegment:
    """A single segment of drafted text with explicit provenance.

    * ``OFFICIAL_FACT`` — carries ``source_reference`` for citation.
    * ``AI_DRAFT`` — carries ``model`` identifier for provenance.

    Validation is **fail-closed**: a segment that violates its source's
    constraints raises ``ValueError`` at construction time.
    """
    text: str
    source: DraftSegmentSource
    source_reference: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("segment text must not be empty")
        if self.source is DraftSegmentSource.OFFICIAL_FACT:
            if not self.source_reference:
                raise ValueError(
                    "OFFICIAL_FACT segment must carry a source_reference"
                )
        elif self.source is DraftSegmentSource.AI_DRAFT:
            if not self.model:
                raise ValueError(
                    "AI_DRAFT segment must carry a model identifier"
                )


@dataclass(frozen=True, slots=True)
class DraftResult:
    """Result of a drafting request.

    * ``available`` is ``False`` when no provider is configured or the
      provider failed — callers degrade gracefully.
    * ``segments`` are ALWAYS explicitly labeled as ``OFFICIAL_FACT`` or
      ``AI_DRAFT`` (acceptance: *Official facts jsou jasně oddělené od
      user/AI obsahu*).
    * ``draft_label`` is an explicit top-level label marking the entire
      result as an AI-generated draft — the *draft label* from the scope.
    """
    available: bool
    segments: tuple[DraftedSegment, ...] = ()
    provider_name: str | None = None
    reason: str | None = None
    draft_label: str = "AI_DRAFT"


@dataclass(frozen=True, slots=True)
class DraftingAuditEvent:
    """Audit event — NEVER stores segment content (privacy)."""
    id: str
    project_id: str | None
    event_type: DraftingAuditEventType
    reason: str | None
    created_at: datetime


class DraftingAuditRepository(Protocol):
    """Records audit events.

    Implementations MUST NOT store segment text or user/project content —
    only event type, project id, and a sanitized reason.
    """
    def append_audit(self, event: DraftingAuditEvent) -> None: ...


class InMemoryDraftingAuditRepository:
    """In-memory audit log for tests / local development."""
    def __init__(self) -> None:
        self.events: list[DraftingAuditEvent] = []

    def append_audit(self, event: DraftingAuditEvent) -> None:
        self.events.append(event)


class DraftingUnauthorizedError(PermissionError):
    """Raised when the caller does not own the project."""


class DraftingAssistant:
    """Grounded application drafting assistant.

    Principles (per issue #362):

    1. **Provider OPTIONAL** — ``provider=None`` → unavailable result
       (no paid hard dependency).
    2. **Official facts separated** from AI content via
       ``DraftSegmentSource``.
    3. **Owner authorization required** — only the project owner may
       draft.
    4. **Fail-closed** on provider / validation errors — caught, returned
       as unavailable results, never propagated as crashes.
    5. **Audit** records event type + reason only — NEVER segment content.
    6. **Does NOT alter grant conditions** — only references official
       facts.

    Reference: ADR-0008.
    """

    DRAFT_LABEL = "AI_DRAFT"

    def __init__(
        self,
        *,
        provider: DraftingProvider | None = None,
        audit: DraftingAuditRepository | None = None,
    ) -> None:
        self.provider = provider
        self.audit = audit or InMemoryDraftingAuditRepository()

    async def draft_application_text(
        self,
        *,
        context: DraftingContext,
        owner_user_id: str,
        project_owner_id: str,
        now: datetime | None = None,
    ) -> DraftResult:
        """Draft application text for a project under a grant call.

        Raises ``DraftingUnauthorizedError`` if the caller is not the
        project owner.  Returns a ``DraftResult`` that is ``available``
        only when a provider is configured and succeeds.
        """
        current = _utc(now)

        # --- Authorization (ADR-0007 capability model) ---
        # Only the project owner may request drafts that reference
        # project-specific data.  This is explicit and checkable.
        if not owner_user_id or owner_user_id != project_owner_id:
            self._audit(
                DraftingAuditEventType.DRAFT_DENIED,
                context.project_id,
                current,
                reason="owner_mismatch",
            )
            raise DraftingUnauthorizedError(
                "only the project owner may draft application text"
            )

        self._audit(
            DraftingAuditEventType.DRAFT_REQUESTED,
            context.project_id,
            current,
        )

        # --- No provider → unavailable (no paid hard dependency) ---
        if self.provider is None:
            self._audit(
                DraftingAuditEventType.DRAFT_UNAVAILABLE,
                context.project_id,
                current,
                reason="provider_not_configured",
            )
            return DraftResult(
                available=False,
                reason="Drafting provider is not configured",
            )

        # --- Fail-closed: provider errors → unavailable result ---
        try:
            segments = await self.provider.draft(context)
        except Exception as exc:
            self._audit(
                DraftingAuditEventType.PROVIDER_ERROR,
                context.project_id,
                current,
                reason=type(exc).__name__,
            )
            return DraftResult(
                available=False,
                provider_name=self.provider.name,
                reason=f"Provider error: {type(exc).__name__}",
            )

        # --- Validate + enforce max_segments ---
        try:
            validated = self._validate_and_truncate(segments, context.max_segments)
        except Exception as exc:
            self._audit(
                DraftingAuditEventType.DRAFT_FAILED,
                context.project_id,
                current,
                reason=type(exc).__name__,
            )
            return DraftResult(
                available=False,
                provider_name=self.provider.name,
                reason=f"Validation error: {type(exc).__name__}",
            )

        self._audit(
            DraftingAuditEventType.DRAFT_COMPLETED,
            context.project_id,
            current,
        )
        return DraftResult(
            available=True,
            segments=tuple(validated),
            provider_name=self.provider.name,
            draft_label=self.DRAFT_LABEL,
        )

    def _validate_and_truncate(
        self,
        segments: list[DraftedSegment],
        max_segments: int,
    ) -> list[DraftedSegment]:
        """Validate provider output and enforce segment cap.

        The dataclass ``__post_init__`` on ``DraftedSegment`` already
        enforces that OFFICIAL_FACT segments carry ``source_reference``
        and AI_DRAFT segments carry ``model``; here we additionally
        guard against a non-conforming provider that returns a bare list
        of non-DraftedSegment objects.
        """
        if not isinstance(segments, list):
            raise ValueError("provider must return a list of DraftedSegment")
        for segment in segments:
            if not isinstance(segment, DraftedSegment):
                raise ValueError(
                    f"provider returned non-DraftedSegment: "
                    f"{type(segment).__name__}"
                )
        return segments[:max_segments]

    def _audit(
        self,
        event_type: DraftingAuditEventType,
        project_id: str,
        now: datetime,
        *,
        reason: str | None = None,
    ) -> None:
        self.audit.append_audit(
            DraftingAuditEvent(
                id=f"drf_{uuid4().hex}",
                project_id=project_id,
                event_type=event_type,
                reason=reason,
                created_at=now,
            )
        )


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)
