from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotacni_majak_source_sdk import (
    AdapterContext,
    FetchState,
    GuardedHttpClient,
    HealthStatus,
    SourceAdapter,
    SourceCheckpoint,
)

from .local_publish import SearchableGrant
from .normalization import GrantNormalizer
from .snapshot import LocalRawSnapshotStore


@dataclass(frozen=True, slots=True)
class GrantCollectionResult:
    grants: tuple[SearchableGrant, ...]
    failures: tuple[str, ...]
    discovered: int
    pages: int


async def collect_searchable_grants(
    *,
    adapter: SourceAdapter,
    normalizer: GrantNormalizer,
    raw_dir: Path,
    limit: int | None = None,
    timeout_seconds: float = 45.0,
    max_response_bytes: int = 30 * 1024 * 1024,
) -> GrantCollectionResult:
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")

    captured_at = datetime.now(timezone.utc)
    raw_dir.mkdir(parents=True, exist_ok=True)
    descriptor = adapter.descriptor

    client_kwargs = dict(
        allowed_hosts=set(descriptor.allowed_hosts),
        requests_per_second=descriptor.requests_per_second,
        max_concurrency=descriptor.max_concurrency,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
    )
    allowed_post_paths = getattr(descriptor, "allowed_post_paths", None)
    if allowed_post_paths:
        client_kwargs["allowed_post_paths"] = set(allowed_post_paths)

    grants: list[SearchableGrant] = []
    failures: list[str] = []
    seen_external_ids: set[str] = set()
    discovered = 0
    pages = 0
    checkpoint: SourceCheckpoint | None = None

    async with GuardedHttpClient(**client_kwargs) as client:
        ctx = AdapterContext(
            run_id=f"local-{descriptor.code.lower()}-{captured_at:%Y%m%dT%H%M%SZ}",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(raw_dir),
            now=captured_at,
        )

        health = await adapter.healthcheck(ctx)
        if health.status == HealthStatus.UNAVAILABLE:
            raise RuntimeError(
                f"{descriptor.code} source unavailable: {health.detail or 'unknown error'}"
            )

        while True:
            page = await adapter.discover(ctx, checkpoint)
            pages += 1
            if not page.items and pages == 1:
                raise RuntimeError(
                    f"{descriptor.code} discovery returned zero records; refusing empty publish"
                )

            for item in page.items:
                if item.external_id in seen_external_ids:
                    continue
                seen_external_ids.add(item.external_id)
                discovered += 1

                if limit is not None and len(grants) >= limit:
                    break

                print(
                    f"[{descriptor.code} {len(grants) + 1}/"
                    f"{limit or page.total_hint or '?'}] "
                    f"{item.external_id} {item.title_hint or ''}"
                )
                try:
                    result = await adapter.fetch_record(ctx, item)
                    if result.state == FetchState.GONE:
                        failures.append(f"{item.external_id}: detail is gone")
                        continue
                    if result.record is None:
                        failures.append(f"{item.external_id}: no record returned")
                        continue
                    grants.append(normalizer.normalize(item, result.record, captured_at))
                except Exception as exc:
                    failures.append(
                        f"{item.external_id}: {type(exc).__name__}: {exc}"
                    )

            if limit is not None and len(grants) >= limit:
                break
            if page.is_complete:
                break
            if page.next_checkpoint is None:
                raise RuntimeError(
                    f"{descriptor.code} incomplete discovery page has no checkpoint"
                )
            checkpoint = page.next_checkpoint

    if not grants:
        raise RuntimeError(
            f"{descriptor.code} refresh produced zero usable records; refusing publish"
        )

    return GrantCollectionResult(
        grants=tuple(grants),
        failures=tuple(failures),
        discovered=discovered,
        pages=pages,
    )
