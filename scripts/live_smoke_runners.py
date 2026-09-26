#!/usr/bin/env python3
"""Unified live-source smoke runner for Dotačni majak.

Runs each connector's healthcheck → discover → fetch_record cycle against
its live source and collects per-source results with explicit status states.

DESIGN PRINCIPLES (per AGENT_HANDOFF.md / ARCHITECTURE.md):
  - READ-ONLY: performs no writes to any external system.
  - UNKNOWN != FAIL: an unexpected error produces UNKNOWN, not FAILURE.
  - Zero-cost-first: never triggers paid operations or auto-pay.
  - Rate safety: GuardedHttpClient with per-source rate limits.
  - Provenance: each result records adapter version and check time.
  - Per-source result: each source gets its own SmokeResult.

This script is invoked ONLY from the scheduled live-smoke GitHub Actions
workflow — NEVER from PR CI. See docs/LIVE_SMOKE.md for details.

Usage:
  python3 scripts/live_smoke_runners.py
  python3 scripts/live_smoke_runners.py --source EU_FT
  python3 scripts/live_smoke_runners.py --json
"""
from __future__ import annotations

import argparse
import asyncio
import importlib as _importlib
import json
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class SmokeStatus(str, Enum):
    """Explicit smoke-test outcome states.

    UNKNOWN != FAIL: an unexpected / unclassifiable error yields UNKNOWN,
    which is a distinct state from HEALTHY, DEGRADED, or UNAVAILABLE.
    """

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class SmokeTarget:
    """Static manifest entry mapping a source to its connector adapter."""

    source_code: str
    source_name: str
    adapter_module: str
    adapter_class: str
    connector_path: str


@dataclass(slots=True)
class SmokeResult:
    """Per-source smoke-test result.

    ``status`` is one of SmokeStatus values.
    ``error`` carries the exception message when status is UNKNOWN or UNAVAILABLE.
    ``detail`` carries human-readable diagnostics (e.g. healthcheck detail).
    """

    source_code: str
    source_name: str
    status: str
    detail: str | None = None
    error: str | None = None
    discovered_count: int | None = None
    adapter_version: str | None = None
    checked_at: str = ""


@dataclass(slots=True)
class SmokeSummary:
    """Aggregate counts across all smoke results."""

    total: int
    healthy: int
    degraded: int
    unavailable: int
    unknown: int
    blocking_sources: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SMOKE_TARGETS manifest
# ---------------------------------------------------------------------------

SMOKE_TARGETS: list[SmokeTarget] = [
    SmokeTarget(
        "EU_FT",
        "EU Funding & Tenders Portal",
        "dotacni_majak_eu_funding",
        "EuFundingTendersAdapter",
        "connectors/eu-funding",
    ),
    SmokeTarget(
        "DOTACEEU",
        "DotaceEU.cz",
        "dotacni_majak_dotaceeu",
        "DotaceEuAdapter",
        "connectors/dotaceeu",
    ),
    SmokeTarget(
        "DZS",
        "Databáze žádostí o socializační služby",
        "dotacni_majak_dzs",
        "DzsAdapter",
        "connectors/dzs",
    ),
    SmokeTarget(
        "IROP",
        "Integrovaný regionální operační program",
        "dotacni_majak_irop",
        "IropAdapter",
        "connectors/irop",
    ),
    SmokeTarget(
        "JDP",
        "Jednotný datový portal",
        "dotacni_majak_jdp",
        "JdpAdapter",
        "connectors/jdp",
    ),
    SmokeTarget(
        "JIHOCESKY",
        "Jihočeský kraj",
        "dotacni_majak_jihocesky",
        "JihoceskyAdapter",
        "connectors/jihocesky",
    ),
    SmokeTarget(
        "KARLOVARSKY",
        "Karlovarský kraj",
        "dotacni_majak_karlovarsky",
        "KarlovarskyAdapter",
        "connectors/karlovarsky",
    ),
    SmokeTarget(
        "KHK",
        "Kraj hlavního města Prahy",
        "dotacni_majak_khk",
        "KhkAdapter",
        "connectors/khk",
    ),
    SmokeTarget(
        "LIBERECKY",
        "Liberecký kraj",
        "dotacni_majak_liberecky",
        "LibereckyAdapter",
        "connectors/liberecky",
    ),
    SmokeTarget(
        "MKCR",
        "Ministerstvo kultury ČR",
        "dotacni_majak_mk",
        "MkAdapter",
        "connectors/mk",
    ),
    SmokeTarget(
        "MMR",
        "Ministerstvo regionálního rozvoje",
        "dotacni_majak_mmr",
        "MmrAdapter",
        "connectors/mmr",
    ),
    SmokeTarget(
        "MODF",
        "Modernizační fond",
        "dotacni_majak_modernization_fund",
        "ModernizationFundAdapter",
        "connectors/modernization-fund",
    ),
    SmokeTarget(
        "MPSV",
        "Ministerstvo práce a sociálních věcí",
        "dotacni_majak_mpsv",
        "MpsvAdapter",
        "connectors/mpsv",
    ),
    SmokeTarget(
        "MSMT",
        "Ministerstvo školství, mládeže a tělovýchovy",
        "dotacni_majak_msmt",
        "MsmtAdapter",
        "connectors/msmt",
    ),
    SmokeTarget(
        "OPJAK",
        "Operace pro kvalitu vzdělanosti (OP JAK)",
        "dotacni_majak_msmt",
        "OpJakAdapter",
        "connectors/msmt",
    ),
    SmokeTarget(
        "MZE_SZIF",
        "Ministerstvo zemědělství – SZIF",
        "dotacni_majak_mze",
        "MzeSzifAdapter",
        "connectors/mze",
    ),
    SmokeTarget(
        "NRB",
        "Národní rozvojová banka",
        "dotacni_majak_nrb",
        "NrbAdapter",
        "connectors/nrb",
    ),
    SmokeTarget(
        "NSA",
        "Národní správa útvarů životního prostředí",
        "dotacni_majak_nsa",
        "NsaAdapter",
        "connectors/nsa",
    ),
    SmokeTarget(
        "OPTAK",
        "Operace pro transformaci a kvalitu",
        "dotacni_majak_optak",
        "OpTakAdapter",
        "connectors/optak",
    ),
    SmokeTarget(
        "OPZP",
        "Operační program zaměstnanost",
        "dotacni_majak_opzp",
        "OpzpAdapter",
        "connectors/opzp",
    ),
    SmokeTarget(
        "PARDUBICKY",
        "Pardubický kraj",
        "dotacni_majak_pardubicky",
        "PardubickyAdapter",
        "connectors/pardubicky",
    ),
    SmokeTarget(
        "PLZENSKY",
        "Plzeňský kraj",
        "dotacni_majak_plzensky",
        "PlzenskyAdapter",
        "connectors/plzensky",
    ),
    SmokeTarget(
        "PRAHA",
        "Hlavní město Praha",
        "dotacni_majak_praha",
        "PrahaAdapter",
        "connectors/praha",
    ),
    SmokeTarget(
        "STREDOCESKY",
        "Středočeský kraj",
        "dotacni_majak_stredocesky",
        "StredoceskyAdapter",
        "connectors/stredocesky",
    ),
    SmokeTarget(
        "TACR",
        "Technická podpora ČR",
        "dotacni_majak_tacr",
        "TacrAdapter",
        "connectors/tacr",
    ),
    SmokeTarget(
        "USTECKY",
        "Ústecký kraj",
        "dotacni_majak_ustecky",
        "UsteckyAdapter",
        "connectors/ustecky",
    ),
    SmokeTarget(
        "VYS",
        "Kraj Vysočina",
        "dotacni_majak_vysocina",
        "VysocinaAdapter",
        "connectors/vysocina",
    ),
]


def validate_targets(targets: list[SmokeTarget]) -> list[str]:
    """Validate SMOKE_TARGETS manifest entries.

    Returns a list of error strings (empty if all valid).
    Does NOT import any connector packages — validation is structural only.
    """
    errors: list[str] = []
    seen_codes: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()

    for t in targets:
        if not t.source_code or not t.source_code.isidentifier():
            errors.append(f"invalid source_code: {t.source_code!r}")
        if not t.source_name:
            errors.append(f"empty source_name for {t.source_code!r}")
        if not t.adapter_module or not t.adapter_module.isidentifier():
            errors.append(f"invalid adapter_module for {t.source_code!r}: {t.adapter_module!r}")
        if not t.adapter_class or not t.adapter_class.isidentifier():
            errors.append(f"invalid adapter_class for {t.source_code!r}: {t.adapter_class!r}")
        if not t.connector_path:
            errors.append(f"empty connector_path for {t.source_code!r}")

        if t.source_code in seen_codes:
            errors.append(f"duplicate source_code: {t.source_code}")
        seen_codes.add(t.source_code)

        if t.adapter_class.isidentifier():
            pair = (t.adapter_module, t.adapter_class)
            if pair in seen_pairs:
                errors.append(
                    f"duplicate adapter entry: {t.adapter_module}.{t.adapter_class}"
                )
            seen_pairs.add(pair)

    return errors


def aggregate_results(results: list[SmokeResult]) -> SmokeSummary:
    """Aggregate SmokeResults into a SmokeSummary with blocking-source list.

    UNKNOWN is NOT treated as a hard failure here — it is surfaced in the
    ``unknown`` count and the ``blocking_sources`` list so callers can decide.
    """
    counts: dict[str, int] = {
        "HEALTHY": 0,
        "DEGRADED": 0,
        "UNAVAILABLE": 0,
        "UNKNOWN": 0,
    }
    blocking: list[str] = []
    for r in results:
        key = r.status.upper()
        if key not in counts:
            key = "UNKNOWN"  # unrecognized status → UNKNOWN
        counts[key] += 1
        if key in ("UNAVAILABLE", "UNKNOWN"):
            blocking.append(r.source_code)
    return SmokeSummary(
        total=len(results),
        healthy=counts["HEALTHY"],
        degraded=counts["DEGRADED"],
        unavailable=counts["UNAVAILABLE"],
        unknown=counts["UNKNOWN"],
        blocking_sources=blocking,
    )


def has_blocking_failures(summary: SmokeSummary) -> bool:
    """Return True if any source is UNAVAILABLE or UNKNOWN (blocking)."""
    return summary.unavailable > 0 or summary.unknown > 0


def format_results(results: list[SmokeResult], summary: SmokeSummary) -> str:
    """Format results for CI output: human-readable lines + JSON artifact."""
    lines: list[str] = []

    lines.append("=== Live Source Smoke Results ===")
    lines.append("")
    for r in results:
        tag = r.status
        detail = r.detail or r.error or ""
        lines.append(f"[{tag}] {r.source_code} ({r.source_name})")
        if detail:
            lines.append(f"  detail: {detail}")
        if r.discovered_count is not None:
            lines.append(f"  discovered: {r.discovered_count}")
        if r.adapter_version:
            lines.append(f"  adapter: v{r.adapter_version}")
        lines.append(f"  checked_at: {r.checked_at}")
        lines.append("")

    lines.append("=== Summary ===")
    lines.append(
        f"Total: {summary.total} | "
        f"Healthy: {summary.healthy} | "
        f"Degraded: {summary.degraded} | "
        f"Unavailable: {summary.unavailable} | "
        f"Unknown: {summary.unknown}"
    )
    if summary.blocking_sources:
        lines.append(f"Blocking sources: {', '.join(summary.blocking_sources)}")
    else:
        lines.append("No blocking failures.")

    json_block = json.dumps(
        {
            "summary": asdict(summary),
            "results": [asdict(r) for r in results],
        },
        indent=2,
        ensure_ascii=False,
    )
    lines.append("")
    lines.append("```json")
    lines.append(json_block)
    lines.append("```")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runtime (requires pydantic / httpx — lazy-imported so module loads without deps)
# ---------------------------------------------------------------------------

def _ensure_connector_path(connector_path: str) -> None:
    """Add a connector's src directory to sys.path so its adapter can be imported."""
    full = ROOT / connector_path / "src"
    path_str = str(full)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _ensure_ingestion_path() -> None:
    """Add ingestion pipelines/src to sys.path for LocalRawSnapshotStore."""
    path_str = str(ROOT / "pipelines" / "ingestion" / "src")
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


async def run_single_smoke(target: SmokeTarget) -> SmokeResult:
    """Execute one connector's smoke cycle against its live source.

    READ-ONLY: healthcheck → discover (page 1) → fetch_record (first item).
    No artifacts are downloaded. No data is written.
    """
    # Lazy imports — pydantic/httpx only needed at runtime
    from dotacni_majak_source_sdk import (
        AdapterContext,
        GuardedHttpClient,
        HealthStatus,
    )

    _ensure_connector_path(target.connector_path)
    _ensure_ingestion_path()

    now = datetime.now(timezone.utc)
    checked_at = now.isoformat()

    try:
        adapter_mod = _importlib.import_module(target.adapter_module)
        adapter_cls = getattr(adapter_mod, target.adapter_class)
        adapter = adapter_cls()
    except Exception as exc:
        return SmokeResult(
            source_code=target.source_code,
            source_name=target.source_name,
            status=SmokeStatus.UNKNOWN.value,
            error=f"adapter import/instantiation failed: {exc!r}",
            checked_at=checked_at,
        )

    adapter_version = getattr(getattr(adapter, "descriptor", None), "adapter_version", None)

    with tempfile.TemporaryDirectory() as tmp:
        try:
            async with GuardedHttpClient(
                allowed_hosts=set(adapter.descriptor.allowed_hosts),
                allowed_post_paths=set(adapter.descriptor.allowed_post_paths),
                requests_per_second=adapter.descriptor.requests_per_second,
                max_concurrency=adapter.descriptor.max_concurrency,
                max_response_bytes=10 * 1024 * 1024,
                max_request_body_bytes=64 * 1024,
            ) as client:
                from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore

                ctx = AdapterContext(
                    run_id="live-smoke",
                    http=client,
                    logger=None,
                    budget=None,
                    now=now,
                    snapshots=LocalRawSnapshotStore(tmp),
                )

                # Step 1: healthcheck
                health = await adapter.healthcheck(ctx)

                if health.status == HealthStatus.UNAVAILABLE:
                    return SmokeResult(
                        source_code=target.source_code,
                        source_name=target.source_name,
                        status=SmokeStatus.UNAVAILABLE.value,
                        detail=health.detail,
                        error=None,
                        adapter_version=adapter_version,
                        checked_at=checked_at,
                    )

                # Step 2: discover (first page only — no paging cursor)
                page = await adapter.discover(ctx, None)
                discovered = len(page.items)

                status = SmokeStatus.HEALTHY.value
                detail_parts: list[str] = []

                if health.status == HealthStatus.DEGRADED:
                    status = SmokeStatus.DEGRADED.value
                    detail_parts.append(f"health: DEGRADED ({health.detail})")
                else:
                    detail_parts.append(f"health: HEALTHY")

                detail_parts.append(f"discovered: {discovered} on first page")

                if discovered == 0:
                    status = SmokeStatus.DEGRADED.value
                    detail_parts.append("no items on first discovery page")

                # Step 3: fetch_record (first item only)
                if page.items:
                    first = page.items[0]
                    result = await adapter.fetch_record(ctx, first)
                    if result.record is None:
                        status = SmokeStatus.DEGRADED.value
                        detail_parts.append("fetch_record returned no record")
                    else:
                        detail_parts.append(
                            f"record: {result.record.external_id} ({result.state.value})"
                        )

                return SmokeResult(
                    source_code=target.source_code,
                    source_name=target.source_name,
                    status=status,
                    detail="; ".join(detail_parts),
                    error=None,
                    discovered_count=discovered,
                    adapter_version=adapter_version,
                    checked_at=checked_at,
                )

        except Exception as exc:
            return SmokeResult(
                source_code=target.source_code,
                source_name=target.source_name,
                status=SmokeStatus.UNKNOWN.value,
                error=f"unexpected error: {exc!r}",
                adapter_version=adapter_version,
                checked_at=checked_at,
            )


async def run_all_smokes(
    targets: list[SmokeTarget] | None = None,
) -> list[SmokeResult]:
    """Run smoke tests for all targets concurrently (max concurrency 3).

    No source is ever written to — this is a read-only health check.
    """
    if targets is None:
        targets = SMOKE_TARGETS

    semaphore = asyncio.Semaphore(3)

    async def _guarded(target: SmokeTarget) -> SmokeResult:
        async with semaphore:
            return await run_single_smoke(target)

    results = await asyncio.gather(*[_guarded(t) for t in targets])
    return list(results)


def main() -> int:
    """CLI entry point. Returns exit code: 0 if all healthy/degraded, 1 if any blocking."""
    parser = argparse.ArgumentParser(
        description="Dotační maják — unified live-source smoke runner (read-only)."
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Run only the specified source code (e.g. EU_FT).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON only (machine-readable).",
    )
    args = parser.parse_args()

    # Validate manifest at startup
    errors = validate_targets(SMOKE_TARGETS)
    if errors:
        for e in errors:
            print(f"MANIFEST ERROR: {e}", file=sys.stderr)
        return 1

    targets = SMOKE_TARGETS
    if args.source:
        targets = [t for t in SMOKE_TARGETS if t.source_code == args.source]
        if not targets:
            print(f"Unknown source code: {args.source}", file=sys.stderr)
            print(f"Available: {', '.join(t.source_code for t in SMOKE_TARGETS)}", file=sys.stderr)
            return 1

    results = asyncio.run(run_all_smokes(targets))
    summary = aggregate_results(results)

    if args.json:
        print(json.dumps({"summary": asdict(summary), "results": [asdict(r) for r in results]}, indent=2, ensure_ascii=False))
    else:
        print(format_results(results, summary))

    return 1 if has_blocking_failures(summary) else 0


if __name__ == "__main__":
    sys.exit(main())
