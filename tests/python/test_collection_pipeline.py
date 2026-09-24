import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.collection import collect_searchable_grants
from dotacni_majak_ingestion.local_publish import SearchableGrant
from dotacni_majak_source_sdk import (
    AdapterContext,
    DiscoveryItem,
    DiscoveryPage,
    FetchState,
    HealthReport,
    HealthStatus,
    NativeRecord,
    RecordFetchResult,
    RetrievalMode,
    SourceAdapter,
    SourceCheckpoint,
    SourceDescriptor,
)


class DummyHttp:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


class FakeAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="FAKE",
        name="Fake",
        authority="OFFICIAL",
        base_url="https://example.com/",
        retrieval_modes=[RetrievalMode.API],
        allowed_hosts=["example.com"],
        adapter_version="1",
    )

    async def healthcheck(self, ctx: AdapterContext):
        return HealthReport(status=HealthStatus.HEALTHY, checked_at=ctx.now)

    async def discover(self, ctx, checkpoint):
        page = int(checkpoint.cursor) if checkpoint and checkpoint.cursor else 1
        if page == 1:
            return DiscoveryPage(
                items=[
                    DiscoveryItem(external_id="a", detail_url="https://example.com/a"),
                    DiscoveryItem(external_id="b", detail_url="https://example.com/b"),
                ],
                next_checkpoint=SourceCheckpoint(cursor="2"),
                is_complete=False,
                total_hint=3,
            )
        return DiscoveryPage(
            items=[
                DiscoveryItem(external_id="b", detail_url="https://example.com/b"),
                DiscoveryItem(external_id="c", detail_url="https://example.com/c"),
            ],
            is_complete=True,
            total_hint=3,
        )

    async def fetch_record(self, ctx, item, validators=None):
        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code="FAKE",
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=item.external_id,
                native_status="OPEN",
                snapshot_ids=["FAKE:" + item.external_id * 64],
            ),
        )

    async def fetch_artifact(self, ctx, artifact, validators=None):
        raise NotImplementedError


class FakeNormalizer:
    def normalize(self, item, record, captured_at):
        digest = (record.external_id * 64)[:64]
        return SearchableGrant(
            source_id="source:fake",
            source_code="FAKE",
            source_name="Fake",
            source_base_url="https://example.com/",
            adapter_key="fake",
            source_external_id=record.external_id,
            source_url=str(record.detail_url),
            content_hash=digest,
            provider_id="provider:fake",
            provider_name="Fake",
            provider_type="NATIONAL",
            programme_id="programme:fake",
            programme_name="Fake",
            funding_origin="CZ_NATIONAL",
            grant_call_id=f"grant:fake:{record.external_id}",
            grant_version_id=f"grant:fake:{record.external_id}:v1",
            canonical_slug=f"fake-{record.external_id}",
            title=record.native_title or record.external_id,
            summary="",
            status="OPEN",
            verification_status="PARTIALLY_VERIFIED",
            captured_at=captured_at.isoformat(),
        )


class CollectionPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_paginates_and_deduplicates_external_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "dotacni_majak_ingestion.collection.GuardedHttpClient",
                return_value=DummyHttp(),
            ):
                result = await collect_searchable_grants(
                    adapter=FakeAdapter(),
                    normalizer=FakeNormalizer(),
                    raw_dir=Path(tmp),
                )
        self.assertEqual(result.pages, 2)
        self.assertEqual(result.discovered, 3)
        self.assertEqual([g.source_external_id for g in result.grants], ["a", "b", "c"])

    async def test_limit_stops_after_requested_grants(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "dotacni_majak_ingestion.collection.GuardedHttpClient",
                return_value=DummyHttp(),
            ):
                result = await collect_searchable_grants(
                    adapter=FakeAdapter(),
                    normalizer=FakeNormalizer(),
                    raw_dir=Path(tmp),
                    limit=2,
                )
        self.assertEqual(len(result.grants), 2)
        self.assertEqual(result.pages, 1)


if __name__ == "__main__":
    unittest.main()
