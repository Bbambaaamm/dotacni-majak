from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REQUIRED_AUTOMATED = {
    "ci",
    "schemaMigrations",
    "regression",
    "searchGolden",
    "eligibility",
    "finance",
    "connectorContracts",
    "sourceSmokes",
    "accessibilityAutomation",
    "productionBuildDryRun",
    "dependencySecurity",
    "usageBudget",
}

REQUIRED_MANUAL = {
    "betaUsability",
    "keyboardAudit",
    "screenReaderAudit",
    "mobileZoomReflowAudit",
    "privacyReview",
    "securityThreatReview",
    "sourceCoverageAudit",
    "provenanceSpotCheck",
    "recoveryTabletop",
    "backupExportRestore",
    "licenseGovernanceReview",
    "incidentContactReview",
}

CHECK_STATUSES = {"PENDING", "PASS", "FAIL", "ACCEPTED_LIMITATION"}
DECISION_STATUSES = {"PENDING", "GO", "NO_GO"}
SHA_RE = re.compile(r"^[a-fA-F0-9]{40}$")


def validate_document(payload: dict[str, Any], *, require_gate: bool) -> list[str]:
    errors: list[str] = []

    if payload.get("schemaVersion") != "1.0":
        errors.append("schemaVersion must be 1.0")

    release = payload.get("release")
    if not isinstance(release, dict):
        errors.append("release must be an object")
        release = {}

    version = release.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("release.version must be a non-empty string")

    sha = release.get("sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        errors.append("release.sha must be a 40-character commit SHA")

    _validate_checks(
        payload.get("automated"),
        REQUIRED_AUTOMATED,
        "automated",
        errors,
        require_gate=require_gate,
    )
    _validate_checks(
        payload.get("manual"),
        REQUIRED_MANUAL,
        "manual",
        errors,
        require_gate=require_gate,
    )

    limitations = payload.get("knownLimitations")
    if not isinstance(limitations, list):
        errors.append("knownLimitations must be a list")
        limitations = []

    ids: set[str] = set()
    for index, limitation in enumerate(limitations):
        prefix = f"knownLimitations[{index}]"
        if not isinstance(limitation, dict):
            errors.append(f"{prefix} must be an object")
            continue

        ident = limitation.get("id")
        summary = limitation.get("summary")
        if not isinstance(ident, str) or not ident.strip():
            errors.append(f"{prefix}.id must be a non-empty string")
        elif ident in ids:
            errors.append(f"duplicate known limitation id: {ident}")
        else:
            ids.add(ident)

        if not isinstance(summary, str) or not summary.strip():
            errors.append(f"{prefix}.summary must be a non-empty string")

        disclosed = limitation.get("publiclyDisclosed")
        accepted = limitation.get("riskAccepted")
        if not isinstance(disclosed, bool):
            errors.append(f"{prefix}.publiclyDisclosed must be boolean")
        if not isinstance(accepted, bool):
            errors.append(f"{prefix}.riskAccepted must be boolean")
        if require_gate and (disclosed is not True or accepted is not True):
            errors.append(
                f"{prefix} must be publicly disclosed and explicitly risk accepted"
            )

    decision = payload.get("decision")
    if not isinstance(decision, dict):
        errors.append("decision must be an object")
        decision = {}

    if decision.get("status") not in DECISION_STATUSES:
        errors.append("decision.status must be PENDING, GO or NO_GO")

    if require_gate:
        if decision.get("status") != "GO":
            errors.append("v1 gate requires explicit decision.status=GO")
        if not decision.get("reviewedAt"):
            errors.append("v1 gate requires decision.reviewedAt")
        reviewer = decision.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            errors.append("v1 gate requires decision.reviewer")
        rationale = decision.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append("v1 gate requires non-empty decision.rationale")

    return errors


def _validate_checks(
    raw: Any,
    required: set[str],
    prefix: str,
    errors: list[str],
    *,
    require_gate: bool,
) -> None:
    if not isinstance(raw, dict):
        errors.append(f"{prefix} must be an object")
        return

    missing = required.difference(raw)
    if missing:
        errors.append(f"{prefix} missing checks: {', '.join(sorted(missing))}")

    unexpected = set(raw).difference(required)
    if unexpected:
        errors.append(
            f"{prefix} has unknown checks: {', '.join(sorted(unexpected))}"
        )

    for key in required.intersection(raw):
        check = raw[key]
        path = f"{prefix}.{key}"
        if not isinstance(check, dict):
            errors.append(f"{path} must be an object")
            continue
        status = check.get("status")
        if status not in CHECK_STATUSES:
            errors.append(f"{path}.status is invalid")
        evidence = check.get("evidence")
        if not isinstance(evidence, str):
            errors.append(f"{path}.evidence must be a string")
            evidence = ""

        if require_gate:
            if status not in {"PASS", "ACCEPTED_LIMITATION"}:
                errors.append(f"{path} must be PASS or ACCEPTED_LIMITATION")
            if not evidence.strip():
                errors.append(f"{path} requires an evidence reference")


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("top-level document must be an object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="release/v1-evidence.json",
        help="v1 release evidence JSON",
    )
    parser.add_argument(
        "--require-gate",
        action="store_true",
        help="Require all human and automated release evidence",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Copy release/v1-evidence.example.json "
            "and replace example values with evidence for a real release candidate."
        )

    try:
        payload = load(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid v1 evidence file: {exc}") from exc

    errors = validate_document(payload, require_gate=args.require_gate)
    if errors:
        raise SystemExit("\n".join(f"- {error}" for error in errors))

    mode = "release gate" if args.require_gate else "structure"
    print(f"OK v1 evidence {mode}: {path}")


if __name__ == "__main__":
    main()
