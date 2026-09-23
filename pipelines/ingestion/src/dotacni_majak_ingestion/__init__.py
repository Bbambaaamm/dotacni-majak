"""Dotační maják ingestion pipeline primitives."""

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
from .snapshot import LocalRawSnapshotStore, RawSnapshot, RawSnapshotStore
from .state import IngestionState, PresenceState

__all__ = [
    "IngestionState",
    "PresenceState",
    "RawSnapshot",
    "RawSnapshotStore",
    "LocalRawSnapshotStore",
    "IngestionItemRecord",
    "IngestionRepository",
    "InMemoryIngestionRepository",
    "IngestionOrchestrator",
    "IngestionRunStatus",
    "IngestionRunSummary",
    "RecordPipeline",
    "PassthroughRecordPipeline",
    "RawSnapshotRequiredError",
]
