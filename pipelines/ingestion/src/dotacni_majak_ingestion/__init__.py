"""Dotační maják ingestion pipeline primitives."""

from .data_quality import (
    QualityGateConfig,
    QualityGateDecision,
    QualityGateStatus,
    QualityViolation,
    SourceRunObservation,
    SourceRunQualityGate,
)
from .orchestrator import (
    InMemoryIngestionRepository,
    IngestionItemRecord,
    IngestionOrchestrator,
    IngestionRepository,
    IngestionRunStatus,
    IngestionRunSummary,
    PassthroughRecordPipeline,
    RawSnapshotRequiredError,
    RecordPipeline,
)
from .outbox import (
    InMemoryOutboxRepository,
    OutboxEvent,
    OutboxEventType,
    OutboxStatus,
)
from .quarantine import (
    InMemoryQuarantineRepository,
    QuarantineItem,
    QuarantineReason,
)
from .health import (
    HealthReason,
    ScheduleHealthInput,
    SourceHealthEvaluator,
    SourceHealthSnapshot,
    SourceHealthStatus,
)
from .snapshot import LocalRawSnapshotStore, RawSnapshot, RawSnapshotStore
from .state import IngestionState, PresenceState

__all__ = [
    "IngestionState", "PresenceState",
    "RawSnapshot", "RawSnapshotStore", "LocalRawSnapshotStore",
    "IngestionItemRecord", "IngestionRepository", "InMemoryIngestionRepository",
    "IngestionOrchestrator", "IngestionRunStatus", "IngestionRunSummary",
    "RecordPipeline", "PassthroughRecordPipeline", "RawSnapshotRequiredError",
    "QualityGateConfig", "QualityGateDecision", "QualityGateStatus",
    "QualityViolation", "SourceRunObservation", "SourceRunQualityGate",
    "HealthReason", "ScheduleHealthInput", "SourceHealthEvaluator",
    "SourceHealthSnapshot", "SourceHealthStatus",
    "OutboxEvent", "OutboxEventType", "OutboxStatus",
    "InMemoryOutboxRepository",
    "QuarantineItem", "QuarantineReason", "InMemoryQuarantineRepository",
]
