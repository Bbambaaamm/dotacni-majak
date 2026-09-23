from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import (
    ArtifactFetchResult,
    DiscoveryItem,
    DiscoveryPage,
    FetchValidators,
    HealthReport,
    RecordFetchResult,
    RemoteArtifactRef,
    SourceCheckpoint,
    SourceDescriptor,
)


@dataclass(slots=True)
class AdapterContext:
    run_id: str
    http: Any
    logger: Any
    budget: Any
    now: datetime
    snapshots: Any | None = None


class SourceAdapter(ABC):
    descriptor: SourceDescriptor

    @abstractmethod
    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        raise NotImplementedError

    @abstractmethod
    async def discover(
        self,
        ctx: AdapterContext,
        checkpoint: SourceCheckpoint | None,
    ) -> DiscoveryPage:
        raise NotImplementedError

    @abstractmethod
    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        raise NotImplementedError

    @abstractmethod
    async def fetch_artifact(
        self,
        ctx: AdapterContext,
        artifact: RemoteArtifactRef,
        validators: FetchValidators | None = None,
    ) -> ArtifactFetchResult:
        raise NotImplementedError
