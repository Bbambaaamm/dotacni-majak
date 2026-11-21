"""Domain tests for dotacni_majak_drafting.

Tests the DraftingAssistant provider-interface contract with NO real LLM
dependency — a deterministic fake provider stands in for the provider
Protocol, exactly as test_semantic_search.py uses MappingProvider.

Covers acceptance criteria from issue #362:
- Ownership/authorization is explicit (owner check + audit)
- Main + error scenarios are automated
- Official facts are clearly separated from AI content (segment sources)
- Draft label is present on the result
- No paywall: provider=None → graceful unavailable
- Fail-closed: provider errors never propagate as crashes
- Privacy: audit events NEVER store segment content
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "drafting" / "src"))

from dotacni_majak_drafting import (
    DraftingAssistant,
    DraftingAuditEvent,
    DraftingAuditEventType,
    DraftingContext,
    DraftingUnauthorizedError,
    DraftResult,
    DraftSegmentSource,
    DraftedSegment,
    InMemoryDraftingAuditRepository,
    OfficialFact,
)

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


# --- Fake providers (stand-ins for the DraftingProvider Protocol) ---

class FakeOkProvider:
    """Deterministic provider that returns properly-labeled segments."""
    name = "fake-ok"

    def __init__(self, segments=None):
        self._segments = segments

    async def draft(self, context: DraftingContext) -> list[DraftedSegment]:
        if self._segments is None:
            return [
                DraftedSegment(
                    text=f"Návrh textu žádosti pro {context.natural_language_intent}.",
                    source=DraftSegmentSource.AI_DRAFT,
                    model=self.name,
                ),
            ]
        return self._segments


class FakeErrorProvider:
    """Provider that always raises."""
    name = "fake-error"

    async def draft(self, context: DraftingContext) -> list[DraftedSegment]:
        raise RuntimeError("provider exploded")


class FakeNonListProvider:
    """Provider that violates the contract by returning a non-list."""
    name = "fake-garbage"

    async def draft(self, context: DraftingContext) -> list[DraftedSegment]:
        return "not a list"  # type: ignore[return-value]


class FakeNonSegmentProvider:
    """Provider that returns strings instead of DraftedSegment."""
    name = "fake-stranger"

    async def draft(self, context: DraftingContext) -> list[DraftedSegment]:
        return ["raw string"]  # type: ignore[list-item]


# --- Helper to build a standard context ---

def make_context(**overrides) -> DraftingContext:
    defaults = dict(
        project_id="prj_00000000000000000000000000000000",
        grant_call_id="gch_test",
        grant_call_version_id="gv_test_v1",
        natural_language_intent="rekonstrukce tenisových kurtů",
        official_facts=(
            OfficialFact(
                content="Podpora až 70 % nákladů.",
                source_reference="nsa:detail:v1:finance",
            ),
        ),
        user_notes="Rozpočet je cca 500 000 Kč.",
        max_segments=10,
    )
    defaults.update(overrides)
    return DraftingContext(**defaults)


class DraftingContextValidationTest(unittest.TestCase):
    """Context dataclass enforces its own contract (fail-closed)."""

    def test_requires_grant_call_version_id(self):
        with self.assertRaises(ValueError):
            DraftingContext(
                project_id="prj_1",
                grant_call_id="gch_1",
                grant_call_version_id="",
                natural_language_intent="intent",
            )

    def test_requires_non_empty_intent(self):
        with self.assertRaises(ValueError):
            DraftingContext(
                project_id="prj_1",
                grant_call_id="gch_1",
                grant_call_version_id="v1",
                natural_language_intent="   ",
            )

    def test_rejects_invalid_max_segments(self):
        for bad in (0, 101, -1):
            with self.subTest(max_segments=bad):
                with self.assertRaises(ValueError):
                    DraftingContext(
                        project_id="prj_1",
                        grant_call_id="gch_1",
                        grant_call_version_id="v1",
                        natural_language_intent="intent",
                        max_segments=bad,
                    )


class DraftedSegmentValidationTest(unittest.TestCase):
    """Segment dataclass enforces provenance constraints (fail-closed)."""

    def test_official_fact_must_have_source_reference(self):
        with self.assertRaises(ValueError):
            DraftedSegment(
                text="Podpora až 70 %",
                source=DraftSegmentSource.OFFICIAL_FACT,
            )

    def test_ai_draft_must_have_model(self):
        with self.assertRaises(ValueError):
            DraftedSegment(
                text="Návrh textu žádosti",
                source=DraftSegmentSource.AI_DRAFT,
            )

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):
            DraftedSegment(
                text="  ",
                source=DraftSegmentSource.OFFICIAL_FACT,
                source_reference="doc:sec",
            )

    def test_valid_official_fact_segment(self):
        seg = DraftedSegment(
            text="Podpora až 70 %.",
            source=DraftSegmentSource.OFFICIAL_FACT,
            source_reference="nsa:detail:v1:finance",
        )
        self.assertEqual(seg.source, DraftSegmentSource.OFFICIAL_FACT)
        self.assertEqual(seg.source_reference, "nsa:detail:v1:finance")

    def test_valid_ai_draft_segment(self):
        seg = DraftedSegment(
            text="Navrhovaný text žádosti...",
            source=DraftSegmentSource.AI_DRAFT,
            model="claude-4",
        )
        self.assertEqual(seg.source, DraftSegmentSource.AI_DRAFT)
        self.assertEqual(seg.model, "claude-4")


class DraftingAssistantHappyPathTest(unittest.IsolatedAsyncioTestCase):
    """Main scenario: owner + provider → available draft result."""

    def setUp(self):
        self.audit = InMemoryDraftingAuditRepository()
        self.context = make_context()

    async def test_owner_drafts_successfully(self):
        provider = FakeOkProvider()
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        result = await assistant.draft_application_text(
            context=self.context,
            owner_user_id="anonymous:prj_00000000000000000000000000000000",
            project_owner_id="anonymous:prj_00000000000000000000000000000000",
            now=NOW,
        )
        self.assertTrue(result.available)
        self.assertEqual(result.provider_name, "fake-ok")
        self.assertEqual(result.draft_label, "AI_DRAFT")
        self.assertEqual(len(result.segments), 1)
        self.assertEqual(
            result.segments[0].source, DraftSegmentSource.AI_DRAFT
        )
        self.assertEqual(result.segments[0].model, "fake-ok")

    async def test_official_facts_and_ai_draft_are_separated(self):
        segments = [
            DraftedSegment(
                text="Podpora až 70 %.",
                source=DraftSegmentSource.OFFICIAL_FACT,
                source_reference="nsa:detail:v1:finance",
            ),
            DraftedSegment(
                text="Navrhuji doplnit údaje o projektech...",
                source=DraftSegmentSource.AI_DRAFT,
                model="fake-ok",
            ),
        ]
        provider = FakeOkProvider(segments=segments)
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        result = await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        self.assertTrue(result.available)
        self.assertEqual(len(result.segments), 2)
        # Official fact is clearly labeled and carries provenance
        self.assertEqual(
            result.segments[0].source, DraftSegmentSource.OFFICIAL_FACT
        )
        self.assertEqual(
            result.segments[0].source_reference, "nsa:detail:v1:finance"
        )
        # AI draft is clearly labeled with model provenance
        self.assertEqual(
            result.segments[1].source, DraftSegmentSource.AI_DRAFT
        )
        self.assertEqual(result.segments[1].model, "fake-ok")

    async def test_max_segments_truncation(self):
        segments = [
            DraftedSegment(
                text=f"Segment {i}",
                source=DraftSegmentSource.AI_DRAFT,
                model="fake-ok",
            )
            for i in range(20)
        ]
        provider = FakeOkProvider(segments=segments)
        context = make_context(max_segments=3)
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        result = await assistant.draft_application_text(
            context=context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        self.assertTrue(result.available)
        self.assertEqual(len(result.segments), 3)

    async def test_empty_provider_output_is_valid(self):
        provider = FakeOkProvider(segments=[])
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        result = await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        self.assertTrue(result.available)
        self.assertEqual(len(result.segments), 0)
        self.assertEqual(result.draft_label, "AI_DRAFT")


class DraftingAssistantNoProviderTest(unittest.IsolatedAsyncioTestCase):
    """No paid hard dependency: provider=None → graceful unavailable."""

    def setUp(self):
        self.audit = InMemoryDraftingAuditRepository()
        self.context = make_context()

    async def test_no_provider_returns_unavailable(self):
        assistant = DraftingAssistant(provider=None, audit=self.audit)
        result = await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        self.assertFalse(result.available)
        self.assertIsNone(result.provider_name)
        self.assertIsNotNone(result.reason)
        self.assertIn("not configured", result.reason)
        self.assertEqual(result.draft_label, "AI_DRAFT")

    async def test_no_provider_records_unavailable_audit(self):
        assistant = DraftingAssistant(provider=None, audit=self.audit)
        await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        types = [e.event_type for e in self.audit.events]
        self.assertIn(DraftingAuditEventType.DRAFT_REQUESTED, types)
        self.assertIn(DraftingAuditEventType.DRAFT_UNAVAILABLE, types)


class DraftingAssistantErrorScenarioTest(unittest.IsolatedAsyncioTestCase):
    """Error scenario: provider exceptions → unavailable, not crash."""

    def setUp(self):
        self.audit = InMemoryDraftingAuditRepository()
        self.context = make_context()

    async def test_provider_error_returns_unavailable(self):
        provider = FakeErrorProvider()
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        result = await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        self.assertFalse(result.available)
        self.assertEqual(result.provider_name, "fake-error")
        self.assertIn("Provider error", result.reason)

    async def test_provider_error_records_provider_error_audit(self):
        provider = FakeErrorProvider()
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        types = [e.event_type for e in self.audit.events]
        self.assertIn(DraftingAuditEventType.PROVIDER_ERROR, types)

    async def test_non_list_output_returns_unavailable(self):
        provider = FakeNonListProvider()
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        result = await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        self.assertFalse(result.available)
        self.assertIn("Validation error", result.reason)

    async def test_non_segment_output_returns_unavailable(self):
        provider = FakeNonSegmentProvider()
        assistant = DraftingAssistant(provider=provider, audit=self.audit)
        result = await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        self.assertFalse(result.available)
        self.assertIn("Validation error", result.reason)


class DraftingAssistantAuthorizationTest(unittest.IsolatedAsyncioTestCase):
    """Ownership/authorization is explicit."""

    def setUp(self):
        self.audit = InMemoryDraftingAuditRepository()
        self.context = make_context()
        self.provider = FakeOkProvider()

    async def test_non_owner_is_denied(self):
        assistant = DraftingAssistant(provider=self.provider, audit=self.audit)
        with self.assertRaises(DraftingUnauthorizedError):
            await assistant.draft_application_text(
                context=self.context,
                owner_user_id="not_the_owner",
                project_owner_id="the_real_owner",
                now=NOW,
            )

    async def test_empty_owner_is_denied(self):
        assistant = DraftingAssistant(provider=self.provider, audit=self.audit)
        with self.assertRaises(DraftingUnauthorizedError):
            await assistant.draft_application_text(
                context=self.context,
                owner_user_id="",
                project_owner_id="the_real_owner",
                now=NOW,
            )

    async def test_owner_mismatch_records_denied_audit(self):
        assistant = DraftingAssistant(provider=self.provider, audit=self.audit)
        with self.assertRaises(DraftingUnauthorizedError):
            await assistant.draft_application_text(
                context=self.context,
                owner_user_id="not_the_owner",
                project_owner_id="the_real_owner",
                now=NOW,
            )
        denied = [
            e for e in self.audit.events
            if e.event_type is DraftingAuditEventType.DRAFT_DENIED
        ]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].project_id, self.context.project_id)
        self.assertEqual(denied[0].reason, "owner_mismatch")

    async def test_owner_does_not_record_denied_audit(self):
        assistant = DraftingAssistant(provider=self.provider, audit=self.audit)
        await assistant.draft_application_text(
            context=self.context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        denied = [
            e for e in self.audit.events
            if e.event_type is DraftingAuditEventType.DRAFT_DENIED
        ]
        self.assertEqual(len(denied), 0)


class DraftingAuditPrivacyTest(unittest.IsolatedAsyncioTestCase):
    """Audit events MUST NEVER store segment content (privacy constraint)."""

    async def test_audit_does_not_contain_segment_text(self):
        audit = InMemoryDraftingAuditRepository()
        context = make_context()
        secret_text = "THIS_IS_A_SECRET_BUDGET_DETAIL_12345"
        segments = [
            DraftedSegment(
                text=secret_text,
                source=DraftSegmentSource.AI_DRAFT,
                model="fake-ok",
            ),
        ]
        provider = FakeOkProvider(segments=segments)
        assistant = DraftingAssistant(provider=provider, audit=audit)
        await assistant.draft_application_text(
            context=context,
            owner_user_id="owner_a",
            project_owner_id="owner_a",
            now=NOW,
        )
        for event in audit.events:
            # Audit events store only event_type, project_id, and a
            # sanitized reason — never segment text or user content.
            blob = str(event)
            self.assertNotIn(secret_text, blob)


class DraftingAuditRepositoryProtocolTest(unittest.TestCase):
    """Verify InMemoryDraftingAuditRepository satisfies the Protocol.

    Protocols in this codebase are NOT @runtime_checkable, so we verify
    the structural contract by calling the method, not via isinstance.
    """

    def test_in_memory_repository_implements_protocol(self):
        repo = InMemoryDraftingAuditRepository()
        event = DraftingAuditEvent(
            id="drf_test",
            project_id="prj_test",
            event_type=DraftingAuditEventType.DRAFT_REQUESTED,
            reason=None,
            created_at=NOW,
        )
        # If this raises, the repository does not satisfy the Protocol.
        repo.append_audit(event)
        self.assertEqual(len(repo.events), 1)
        self.assertEqual(repo.events[0].event_type,
                         DraftingAuditEventType.DRAFT_REQUESTED)


if __name__ == "__main__":
    unittest.main()
