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
    "OutboxEvent", "OutboxEventType", "OutboxStatus",
    "InMemoryOutboxRepository",
    "QuarantineItem", "QuarantineReason", "InMemoryQuarantineRepository",
]

from .quality import QualityDecision, SourceRunMetrics, SourceRunQuality, SourceRunQualityGate
from .quarantine import DataQualityIssue, DataQualitySeverity, QuarantineItem, ValidationResult
from .outbox import OutboxEvent, OutboxEventType, OutboxStatus
