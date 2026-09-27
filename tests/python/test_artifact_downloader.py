import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.artifacts import (
    ArtifactCacheEntry,
    ArtifactDownloadError,
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
    NativeRecord,
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

ARTIFACT_2 = RemoteArtifactRef(
    external_id="doc-2",
    url="https://example.com/doc2.html",
    role="CALL_DOCUMENT",
    mime_hint="text/html",
)

RECORD_WITH_ARTIFACTS = NativeRecord(
    source_code="TEST",
    external_id="rec-1",
    detail_url="https://example.com/rec-1",
    artifacts=[ARTIFACT, ARTIFACT_2],
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


class ArtifactDownloaderEdgeCaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_download_record_artifacts_batch_multiple(self):
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
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "b" * 64,
                sha256="b" * 64,
                mime_type="text/html",
                size_bytes=200,
                etag='"v2"',
                last_modified="Wed, 24 Sep 2026 07:00:00 GMT",
            ),
        ])
        cache = InMemoryArtifactCacheRepository()
        downloader = ArtifactDownloader(cache=cache)
        results = await downloader.download_record_artifacts(
            adapter=adapter, ctx=CTX, record=RECORD_WITH_ARTIFACTS
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].state, ArtifactObservedState.MODIFIED)
        self.assertEqual(results[1].state, ArtifactObservedState.MODIFIED)
        self.assertEqual(results[0].snapshot_id, "TEST:" + "a" * 64)
        self.assertEqual(results[1].snapshot_id, "TEST:" + "b" * 64)
        self.assertEqual(cache.get("TEST", ARTIFACT).snapshot_id, "TEST:" + "a" * 64)
        self.assertEqual(cache.get("TEST", ARTIFACT_2).snapshot_id, "TEST:" + "b" * 64)

    async def test_download_record_artifacts_empty(self):
        adapter = FakeAdapter([])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
        )
        record = NativeRecord(
            source_code="TEST",
            external_id="rec-empty",
            detail_url="https://example.com/rec-empty",
            artifacts=[],
        )
        results = await downloader.download_record_artifacts(
            adapter=adapter, ctx=CTX, record=record
        )
        self.assertEqual(results, ())

    async def test_unknown_mime_rejected_when_configured(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "c" * 64,
                sha256="c" * 64,
                mime_type=None,
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

    async def test_none_mime_allowed_when_unknown_policy_permits(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "d" * 64,
                sha256="d" * 64,
                mime_type=None,
                size_bytes=10,
            ),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
            policy=ArtifactDownloadPolicy(reject_unknown_mime=False),
        )
        result = await downloader.download(
            adapter=adapter,
            ctx=CTX,
            artifact=ARTIFACT,
        )
        self.assertEqual(result.state, ArtifactObservedState.MODIFIED)
        self.assertIsNone(result.mime_type)

    async def test_error_hierarchy_is_artifact_download_error(self):
        self.assertTrue(issubclass(ArtifactInvariantError, ArtifactDownloadError))
        self.assertTrue(issubclass(ArtifactMimeRejected, ArtifactDownloadError))
        self.assertIsInstance(
            ArtifactInvariantError("test"), ArtifactDownloadError
        )
        self.assertIsInstance(
            ArtifactMimeRejected("test"), ArtifactDownloadError
        )

    async def test_gone_without_previous_cache(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(state=FetchState.GONE),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
        )
        result = await downloader.download(
            adapter=adapter,
            ctx=CTX,
            artifact=ARTIFACT,
        )
        self.assertEqual(result.state, ArtifactObservedState.GONE)
        self.assertIsNone(result.previous_snapshot_id)

    async def test_cache_key_isolation_per_source(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.NOT_MODIFIED,
            ),
        ])
        cache = InMemoryArtifactCacheRepository()
        cache.put(ArtifactCacheEntry(
            source_code="OTHER_SOURCE",
            external_id=ARTIFACT.external_id,
            url=str(ARTIFACT.url),
            snapshot_id="TEST:" + "e" * 64,
            sha256="e" * 64,
        ))
        downloader = ArtifactDownloader(cache=cache)
        with self.assertRaises(ArtifactInvariantError):
            await downloader.download(
                adapter=adapter, ctx=CTX, artifact=ARTIFACT
            )

    async def test_conditional_request_passes_sha256_validator(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "f" * 64,
                sha256="f" * 64,
                mime_type="application/pdf",
                size_bytes=100,
                etag='"v1"',
                last_modified="Wed, 24 Sep 2026 06:00:00 GMT",
            ),
            ArtifactFetchResult(
                state=FetchState.NOT_MODIFIED,
            ),
        ])
        downloader = ArtifactDownloader(cache=InMemoryArtifactCacheRepository())
        await downloader.download(adapter=adapter, ctx=CTX, artifact=ARTIFACT)
        second = await downloader.download(
            adapter=adapter, ctx=CTX, artifact=ARTIFACT
        )
        validators = adapter.validators[1]
        self.assertIsNotNone(validators)
        self.assertEqual(validators.known_sha256, "f" * 64)

    async def test_custom_allowed_mime_types(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(
                state=FetchState.MODIFIED,
                snapshot_id="TEST:" + "g" * 64,
                sha256="g" * 64,
                mime_type="application/json",
                size_bytes=100,
            ),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
            policy=ArtifactDownloadPolicy(
                allowed_mime_types=frozenset({"application/json"}),
            ),
        )
        result = await downloader.download(
            adapter=adapter, ctx=CTX, artifact=ARTIFACT
        )
        self.assertEqual(result.state, ArtifactObservedState.MODIFIED)

    async def test_gone_in_batch_without_cache(self):
        adapter = FakeAdapter([
            ArtifactFetchResult(state=FetchState.GONE),
            ArtifactFetchResult(state=FetchState.GONE),
        ])
        downloader = ArtifactDownloader(
            cache=InMemoryArtifactCacheRepository(),
            policy=ArtifactDownloadPolicy(reject_unknown_mime=False),
        )
        results = await downloader.download_record_artifacts(
            adapter=adapter, ctx=CTX, record=RECORD_WITH_ARTIFACTS
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].state, ArtifactObservedState.GONE)
        self.assertEqual(results[1].state, ArtifactObservedState.GONE)
        self.assertIsNone(results[0].previous_snapshot_id)


if __name__ == "__main__":
    unittest.main()
