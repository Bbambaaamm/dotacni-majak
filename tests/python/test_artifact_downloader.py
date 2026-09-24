import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.artifacts import (
    ArtifactDownloadPolicy,
    ArtifactDownloader,
    ArtifactInvariantError,
    ArtifactMimeRejected,
    ArtifactObservedState,
    InMemoryArtifactCacheRepository,
)
from dotacni_majak_source_sdk import (
    AdapterContext,
    ArtifactFetchResult,
    FetchState,
    HealthReport,
    HealthStatus,
    RecordFetchResult,
    RemoteArtifactRef,
    RetrievalMode,
    SourceAdapter,
    SourceDescriptor,
)


ARTIFACT = RemoteArtifactRef(
    external_id="doc-1",
    url="https://example.com/doc.pdf",
    role="CALL_DOCUMENT",
    mime_hint="application/pdf",
)


class FakeAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="TEST",
        name="Test",
        authority="OFFICIAL",
        base_url="https://example.com/",
        retrieval_modes=[RetrievalMode.HTML, RetrievalMode.PDF],
        allowed_hosts=["example.com"],
        adapter_version="1",
    )

    def __init__(self, results):
        self.results = list(results)
        self.validators = []

    async def healthcheck(self, ctx):
        return HealthReport(status=HealthStatus.HEALTHY, checked_at=ctx.now)

    async def discover(self, ctx, checkpoint):
        raise NotImplementedError

    async def fetch_record(self, ctx, item, validators=None):
        raise NotImplementedError

    async def fetch_artifact(self, ctx, artifact, validators=None):
        self.validators.append(validators)
        return self.results.pop(0)


CTX = AdapterContext(
    run_id="r1",
    http=None,
    logger=None,
    budget=None,
    snapshots=None,
    now=datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc),
)


class ArtifactDownloaderTest(unittest.IsolatedAsyncioTestCase):
    async def test_modified_then_not_modified_reuses_snapshot_and_validators(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "a" * 64,
                sha256="a" * 64,
                mime_type="application/pdf",
                size_bytes=100,
                etag='"v1"',
                last_modified="Wed, 24 Sep 2026 06:00:00 GMT",
            ),
            ArtifactFetchResult(
                state=FetchState.NOT_MODIFIED,
                etag='"v1"',
            ),
        ])
        cache = InMemoryArtifactCacheRepository()
        downloader = ArtifactDownloader(cache=cache)

        first = await downloader.download(
            adapter=adapter,
            ctx=CTX,
            artifact=ARTIFACT,
        )
        second = await downloader.download(
            adapter=adapter,
            ctx=CTX,
            artifact=ARTIFACT,
        )

        self.assertEqual(first.state, ArtifactObservedState.MODIFIED)
        self.assertEqual(second.state, ArtifactObservedState.REUSED)
        self.assertEqual(second.snapshot_id, first.snapshot_id)
        self.assertIsNone(adapter.validators[0])
        self.assertEqual(adapter.validators[1].etag, '"v1"')
        self.assertEqual(adapter.validators[1].known_sha256, "a" * 64)

    async def test_not_modified_without_cached_snapshot_is_rejected(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(state=FetchState.NOT_MODIFIED),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
        )
        with self.assertRaises(ArtifactInvariantError):
            await downloader.download(
                adapter=adapter,
                ctx=CTX,
                artifact=ARTIFACT,
            )

    async def test_modified_without_snapshot_is_rejected(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                mime_type="application/pdf",
            ),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
        )
        with self.assertRaises(ArtifactInvariantError):
            await downloader.download(
                adapter=adapter,
                ctx=CTX,
                artifact=ARTIFACT,
            )

    async def test_disallowed_mime_is_rejected(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "b" * 64,
                sha256="b" * 64,
                mime_type="application/x-msdownload",
                size_bytes=10,
            ),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
            policy=ArtifactDownloadPolicy(reject_unknown_mime=True),
        )
        with self.assertRaises(ArtifactMimeRejected):
            await downloader.download(
                adapter=adapter,
                ctx=CTX,
                artifact=ARTIFACT,
            )

    async def test_gone_preserves_previous_snapshot_reference_for_audit(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "c" * 64,
                sha256="c" * 64,
                mime_type="application/pdf",
                size_bytes=10,
            ),
            ArtifactFetchResult(state=FetchState.GONE),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
        )
        first = await downloader.download(
            adapter=adapter,
            ctx=CTX,
            artifact=ARTIFACT,
        )
        gone = await downloader.download(
            adapter=adapter,
            ctx=CTX,
            artifact=ARTIFACT,
        )
        self.assertEqual(gone.state, ArtifactObservedState.GONE)
        self.assertEqual(gone.previous_snapshot_id, first.snapshot_id)


if __name__ == "__main__":
    unittest.main()
