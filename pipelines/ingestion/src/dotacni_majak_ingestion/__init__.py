"""Dotační maják ingestion pipeline primitives."""

from .artifacts import (
    ArtifactCacheEntry,
    ArtifactCacheRepository,
    ArtifactDownloadError,
    ArtifactDownloadPolicy,
    ArtifactDownloader,
    ArtifactInvariantError,
    ArtifactMimeRejected,
    ArtifactObservedState,
    DownloadedArtifact,
    InMemoryArtifactCacheRepository,
)
from .document_model import BlockKind, ParsedBlock, ParsedDocument, SourceAnchor\nfrom .html_parser import HtmlDocumentError, HtmlParserPolicy, parse_html_document\nfrom .document_security import (
    DocumentKind,
    DocumentSecurityError,
    DocumentSecurityPolicy,
    InspectedDocument,
    OcrDecision,
    inspect_document,
    ocr_decision,
)
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
    IngestionLockLostError,
    IngestionOrchestrator,
    IngestionRepository,
    IngestionRunStatus,
    IngestionRunSummary,
    PassthroughRecordPipeline,
    RawSnapshotRequiredError,
    RecordPipeline,
)
from .collection import GrantCollectionResult, collect_searchable_grants
from .normalization import (
    DotaceEuGrantNormalizer,
    EuFundingGrantNormalizer,
    GrantNormalizer,
    NsaGrantNormalizer,
    canonical_status,
    normalizer_for,
    record_content_hash,
    stable_programme_identity,
)
from .outbox import (
    InMemoryOutboxRepository,
    OutboxEvent,
    OutboxEventType,
    OutboxStatus,
)
from .outbox_worker import (
    OutboxHandler,
    OutboxWorker,
    OutboxWorkerResult,
    RetryPolicy,
)
from .sqlite_outbox import OutboxLeaseError, SqliteOutboxRepository
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
from .sqlite_repository import SqliteIngestionRepository
from .state import IngestionState, PresenceState

__all__ = [
    "ArtifactCacheEntry", "ArtifactCacheRepository", "ArtifactDownloadError",
    "ArtifactDownloadPolicy", "ArtifactDownloader", "ArtifactInvariantError",
    "ArtifactMimeRejected", "ArtifactObservedState", "DownloadedArtifact",
    "InMemoryArtifactCacheRepository",
    "BlockKind", "ParsedBlock", "ParsedDocument", "SourceAnchor",\n    "HtmlDocumentError", "HtmlParserPolicy", "parse_html_document",\n    "DocumentKind", "DocumentSecurityError", "DocumentSecurityPolicy",
    "InspectedDocument", "OcrDecision", "inspect_document", "ocr_decision",
    "IngestionState", "PresenceState",
    "RawSnapshot", "RawSnapshotStore", "LocalRawSnapshotStore",
    "IngestionItemRecord", "IngestionLockLostError", "IngestionRepository",
    "InMemoryIngestionRepository", "SqliteIngestionRepository",
    "IngestionOrchestrator", "IngestionRunStatus", "IngestionRunSummary",
    "RecordPipeline", "PassthroughRecordPipeline", "RawSnapshotRequiredError",
    "QualityGateConfig", "QualityGateDecision", "QualityGateStatus",
    "QualityViolation", "SourceRunObservation", "SourceRunQualityGate",
    "HealthReason", "ScheduleHealthInput", "SourceHealthEvaluator",
    "SourceHealthSnapshot", "SourceHealthStatus",
    "GrantCollectionResult", "collect_searchable_grants",
    "GrantNormalizer", "NsaGrantNormalizer", "DotaceEuGrantNormalizer",
    "EuFundingGrantNormalizer", "canonical_status", "normalizer_for",
    "record_content_hash", "stable_programme_identity",
    "OutboxEvent", "OutboxEventType", "OutboxStatus",
    "InMemoryOutboxRepository", "SqliteOutboxRepository", "OutboxLeaseError",
    "OutboxHandler", "OutboxWorker", "OutboxWorkerResult", "RetryPolicy",
    "QuarantineItem", "QuarantineReason", "InMemoryQuarantineRepository",
]
