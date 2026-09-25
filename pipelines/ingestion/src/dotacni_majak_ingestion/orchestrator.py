from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from dotacni_majak_source_sdk import (
    AdapterContext,
    FetchState,
    HealthStatus,
    NativeRecord,
    SourceAdapter,
    SourceCheckpoint,
)

from .state import IngestionState


class IngestionRunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    PARTIAL_FAILED = "PARTIAL_FAILED"
    LOCKED = "LOCKED"
    FAILED = "FAILED"


@dataclass(slots=True)
class IngestionItemRecord:
    source_code: str
    external_id: str
    state: IngestionState = IngestionState.DISCOVERED
    attempts: int = 0
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionRunSummary:
    source_code: str
    status: IngestionRunStatus
    processed: int = 0
    skipped: int = 0
    gone: int = 0
    failed: int = 0
    pages: int = 0


class IngestionRepository(ABC):
    @abstractmethod
    def get_checkpoint(self, source_code: str) -> SourceCheckpoint | None:
        raise NotImplementedError

    @abstractmethod
    def set_checkpoint(
        self,
        source_code: str,
        checkpoint: SourceCheckpoint,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_or_create_item(
        self,
        source_code: str,
        external_id: str,
    ) -> IngestionItemRecord:
        raise NotImplementedError

    @abstractmethod
    def transition(
        self,
        item: IngestionItemRecord,
        state: IngestionState,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def fail(
        self,
        item: IngestionItemRecord,
        error: Exception,
    ) -> None:
        raise NotImplementedError

    # Persistence/lifecycle hooks intentionally have safe no-op defaults so the
    # reference in-memory repository remains useful in focused unit tests.
    def acquire_lock(
        self,
        source_code: str,
        owner: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        del source_code, owner, now, lease_seconds
        return True

    def renew_lock(
        self,
        source_code: str,
        owner: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        del source_code, owner, now, lease_seconds
        return True

    def release_lock(self, source_code: str, owner: str) -> None:
        del source_code, owner

    def start_run(
        self,
        source_code: str,
        *,
        started_at: datetime,
        checkpoint_before: SourceCheckpoint | None,
    ) -> None:
        del source_code, started_at, checkpoint_before

    def finish_run(
        self,
        summary: IngestionRunSummary,
        *,
        finished_at: datetime,
        checkpoint_after: SourceCheckpoint | None,
        last_error: str | None = None,
    ) -> None:
        del summary, finished_at, checkpoint_after, last_error


class InMemoryIngestionRepository(IngestionRepository):
    """Reference repository for tests/local development."""

    def __init__(self) -> None:
        self.checkpoints: dict[str, SourceCheckpoint] = {}
        self.items: dict[tuple[str, str], IngestionItemRecord] = {}
        self.transitions: list[tuple[str, str, IngestionState]] = []

    def get_checkpoint(self, source_code: str) -> SourceCheckpoint | None:
        return self.checkpoints.get(source_code)

    def set_checkpoint(
        self,
        source_code: str,
        checkpoint: SourceCheckpoint,
    ) -> None:
        self.checkpoints[source_code] = checkpoint

    def get_or_create_item(
        self,
        source_code: str,
        external_id: str,
    ) -> IngestionItemRecord:
        key = (source_code, external_id)
        if key not in self.items:
            self.items[key] = IngestionItemRecord(
                source_code=source_code,
                external_id=external_id,
            )
        return self.items[key]

    def transition(
        self,
        item: IngestionItemRecord,
        state: IngestionState,
    ) -> None:
        item.state = state
        item.last_error = None
        self.transitions.append((item.source_code, item.external_id, state))

    def fail(
        self,
        item: IngestionItemRecord,
        error: Exception,
    ) -> None:
        item.attempts += 1
        item.last_error = f"{type(error).__name__}: {error}"
        item.state = IngestionState.RETRYABLE_FAILED
        self.transitions.append(
            (item.source_code, item.external_id, IngestionState.RETRYABLE_FAILED)
        )


class RecordPipeline(Protocol):
    async def parse(self, record: NativeRecord) -> Any: ...
    async def extract(self, parsed: Any) -> Any: ...
    async def normalize(self, extracted: Any) -> Any: ...
    async def validate(self, normalized: Any) -> Any: ...
    async def stage(self, validated: Any) -> Any: ...
    async def publish(self, staged: Any) -> Any: ...
    async def index(self, published: Any) -> Any: ...


class PassthroughRecordPipeline:
    async def parse(self, record: NativeRecord) -> Any:
        return record

    async def extract(self, parsed: Any) -> Any:
        return parsed

    async def normalize(self, extracted: Any) -> Any:
        return extracted

    async def validate(self, normalized: Any) -> Any:
        return normalized

    async def stage(self, validated: Any) -> Any:
        return validated

    async def publish(self, staged: Any) -> Any:
        return staged

    async def index(self, published: Any) -> Any:
        return published


class RawSnapshotRequiredError(RuntimeError):
    pass


class IngestionLockLostError(RuntimeError):
    pass


class IngestionOrchestrator:
    def __init__(
        self,
        *,
        repository: IngestionRepository,
        pipeline: RecordPipeline,
        lease_seconds: int = 15 * 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")
        self.repository = repository
        self.pipeline = pipeline
        self.lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("orchestrator clock must return timezone-aware datetime")
        return value.astimezone(timezone.utc)

    async def run(
        self,
        adapter: SourceAdapter,
        ctx: AdapterContext,
    ) -> IngestionRunSummary:
        source_code = adapter.descriptor.code
        owner = ctx.run_id
        lock_now = self._now()

        if not self.repository.acquire_lock(
            source_code,
            owner,
            now=lock_now,
            lease_seconds=self.lease_seconds,
        ):
            summary = IngestionRunSummary(
                source_code=source_code,
                status=IngestionRunStatus.LOCKED,
            )
            # A lock miss is still observable as a run attempt.
            checkpoint = self.repository.get_checkpoint(source_code)
            self.repository.start_run(
                source_code,
                started_at=ctx.now,
                checkpoint_before=checkpoint,
            )
            self.repository.finish_run(
                summary,
                finished_at=self._now(),
                checkpoint_after=checkpoint,
                last_error="source ingestion lock is already held",
            )
            return summary

        summary: IngestionRunSummary | None = None
        last_error: str | None = None
        run_started = False
        checkpoint_before: SourceCheckpoint | None = None
        try:
            checkpoint_before = self.repository.get_checkpoint(source_code)
            self.repository.start_run(
                source_code,
                started_at=ctx.now,
                checkpoint_before=checkpoint_before,
            )
            run_started = True

            health = await adapter.healthcheck(ctx)
            if health.status == HealthStatus.UNAVAILABLE:
                summary = IngestionRunSummary(
                    source_code=source_code,
                    status=IngestionRunStatus.SOURCE_UNAVAILABLE,
                )
                return summary

            summary = await self._run_pages(
                adapter,
                ctx,
                checkpoint_before,
            )
            return summary
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            summary = IngestionRunSummary(
                source_code=source_code,
                status=IngestionRunStatus.FAILED,
            )
            raise
        finally:
            try:
                if run_started and summary is not None:
                    self.repository.finish_run(
                        summary,
                        finished_at=self._now(),
                        checkpoint_after=self.repository.get_checkpoint(source_code),
                        last_error=last_error,
                    )
            finally:
                self.repository.release_lock(source_code, owner)

    async def _run_pages(
        self,
        adapter: SourceAdapter,
        ctx: AdapterContext,
        checkpoint: SourceCheckpoint | None,
    ) -> IngestionRunSummary:
        source_code = adapter.descriptor.code
        processed = skipped = gone = failed = pages = 0

        while True:
            page = await adapter.discover(ctx, checkpoint)
            pages += 1
            page_failed = False

            for discovery_item in page.items:
                item = self.repository.get_or_create_item(
                    source_code,
                    discovery_item.external_id,
                )

                if item.state == IngestionState.COMPLETED:
                    skipped += 1
                    continue

                try:
                    outcome = await self._process_item(
                        adapter,
                        ctx,
                        item,
                        discovery_item,
                    )
                except Exception as exc:
                    self.repository.fail(item, exc)
                    failed += 1
                    page_failed = True
                    continue

                if outcome == "gone":
                    gone += 1
                elif outcome == "skipped":
                    skipped += 1
                else:
                    processed += 1

            if page_failed:
                return IngestionRunSummary(
                    source_code=source_code,
                    status=IngestionRunStatus.PARTIAL_FAILED,
                    processed=processed,
                    skipped=skipped,
                    gone=gone,
                    failed=failed,
                    pages=pages,
                )

            # Renew the source lease before committing progress. Losing the
            # lease means another worker may have taken ownership, so we must
            # stop before advancing the checkpoint.
            if not self.repository.renew_lock(
                source_code,
                ctx.run_id,
                now=self._now(),
                lease_seconds=self.lease_seconds,
            ):
                raise IngestionLockLostError(
                    f"lost ingestion lease for source {source_code}"
                )

            if page.next_checkpoint is not None:
                self.repository.set_checkpoint(
                    source_code,
                    page.next_checkpoint,
                )
                checkpoint = page.next_checkpoint

            if page.is_complete:
                return IngestionRunSummary(
                    source_code=source_code,
                    status=IngestionRunStatus.COMPLETED,
                    processed=processed,
                    skipped=skipped,
                    gone=gone,
                    failed=failed,
                    pages=pages,
                )

            if page.next_checkpoint is None:
                raise RuntimeError(
                    "incomplete discovery page must provide next_checkpoint"
                )

    async def _process_item(
        self,
        adapter: SourceAdapter,
        ctx: AdapterContext,
        item: IngestionItemRecord,
        discovery_item: Any,
    ) -> str:
        self.repository.transition(item, IngestionState.FETCHING)
        fetched = await adapter.fetch_record(ctx, discovery_item, None)

        if fetched.state == FetchState.GONE:
            self.repository.transition(item, IngestionState.COMPLETED)
            return "gone"

        if fetched.state == FetchState.NOT_MODIFIED:
            self.repository.transition(item, IngestionState.COMPLETED)
            return "skipped"

        if fetched.record is None:
            raise RuntimeError("MODIFIED fetch result must contain record")

        record = fetched.record
        self.repository.transition(item, IngestionState.FETCHED)

        artifact_snapshot_ids: list[str] = []
        for artifact in record.artifacts:
            artifact_result = await adapter.fetch_artifact(
                ctx,
                artifact,
                None,
            )
            if (
                artifact_result.state == FetchState.MODIFIED
                and artifact_result.snapshot_id is None
            ):
                raise RawSnapshotRequiredError(
                    f"artifact {artifact.external_id!r} was modified "
                    "but has no RAW snapshot_id"
                )
            if artifact_result.snapshot_id:
                artifact_snapshot_ids.append(artifact_result.snapshot_id)

        if not record.snapshot_ids and not artifact_snapshot_ids:
            raise RawSnapshotRequiredError(
                "modified source record must reference at least one RAW snapshot"
            )

        self.repository.transition(item, IngestionState.SNAPSHOTTED)

        parsed = await self.pipeline.parse(record)
        self.repository.transition(item, IngestionState.PARSED)

        extracted = await self.pipeline.extract(parsed)
        self.repository.transition(item, IngestionState.EXTRACTED)

        normalized = await self.pipeline.normalize(extracted)
        self.repository.transition(item, IngestionState.NORMALIZED)

        validated = await self.pipeline.validate(normalized)
        self.repository.transition(item, IngestionState.VALIDATED)

        staged = await self.pipeline.stage(validated)
        self.repository.transition(item, IngestionState.STAGED)

        published = await self.pipeline.publish(staged)
        self.repository.transition(item, IngestionState.PUBLISHED)

        await self.pipeline.index(published)
        self.repository.transition(item, IngestionState.INDEXED)
        self.repository.transition(item, IngestionState.COMPLETED)
        return "processed"
