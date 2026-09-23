from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SEGMENTS = {"OBEC", "SPOLEK", "OBCAN", "FIRMA", "SKOLA"}
TASKS = {"A", "B", "C", "D", "E", "F"}
BLOCKING_SEVERITIES = {"P0", "P1"}
OPEN_FINDING_STATES = {"OPEN", "RETEST_REQUIRED"}


class BetaResearchError(ValueError):
    pass


def validate_document(payload: dict[str, Any], *, require_gate: bool) -> list[str]:
    errors: list[str] = []

    if payload.get("schemaVersion") != "1.0":
        errors.append("schemaVersion must be 1.0")

    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        errors.append("sessions must be a list")
        sessions = []

    seen_ids: set[str] = set()
    segments: set[str] = set()
    task_counts = {task: 0 for task in TASKS}

    for index, session in enumerate(sessions):
        prefix = f"sessions[{index}]"
        if not isinstance(session, dict):
            errors.append(f"{prefix} must be an object")
            continue

        session_id = session.get("id")
        if not isinstance(session_id, str) or not session_id:
            errors.append(f"{prefix}.id must be a non-empty string")
        elif session_id in seen_ids:
            errors.append(f"duplicate session id: {session_id}")
        else:
            seen_ids.add(session_id)

        segment = session.get("segment")
        if segment not in SEGMENTS:
            errors.append(f"{prefix}.segment must be one of {sorted(SEGMENTS)}")
        else:
            segments.add(segment)

        tasks = session.get("tasks")
        if not isinstance(tasks, list):
            errors.append(f"{prefix}.tasks must be a list")
            continue

        seen_session_tasks: set[str] = set()
        for task_index, task in enumerate(tasks):
            task_prefix = f"{prefix}.tasks[{task_index}]"
            if not isinstance(task, dict):
                errors.append(f"{task_prefix} must be an object")
                continue
            task_id = task.get("id")
            if task_id not in TASKS:
                errors.append(f"{task_prefix}.id must be A-F")
                continue
            if task_id in seen_session_tasks:
                errors.append(f"{prefix} duplicates task {task_id}")
                continue
            seen_session_tasks.add(task_id)
            task_counts[task_id] += 1

            for key in ("completedWithoutHelp", "criticalMisunderstanding"):
                if not isinstance(task.get(key), bool):
                    errors.append(f"{task_prefix}.{key} must be boolean")

            for key in ("sourceFound", "correctNextAction"):
                value = task.get(key)
                if value is not None and not isinstance(value, bool):
                    errors.append(f"{task_prefix}.{key} must be boolean or null")

    findings = payload.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []

    open_blockers: list[str] = []
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        severity = finding.get("severity")
        state = finding.get("status")
        if severity not in {"P0", "P1", "P2", "P3"}:
            errors.append(f"{prefix}.severity must be P0-P3")
        if state not in {"OPEN", "FIXED", "RETEST_REQUIRED", "VERIFIED"}:
            errors.append(f"{prefix}.status is invalid")
        if severity in BLOCKING_SEVERITIES and state in OPEN_FINDING_STATES:
            open_blockers.append(str(finding.get("id", prefix)))

    decision = payload.get("decision")
    if not isinstance(decision, dict):
        errors.append("decision must be an object")
        decision = {}
    if decision.get("status") not in {"PENDING", "GO", "NO_GO"}:
        errors.append("decision.status must be PENDING, GO or NO_GO")

    if require_gate:
        missing_segments = SEGMENTS.difference(segments)
        if missing_segments:
            errors.append(
                "beta gate missing representative segment(s): "
                + ", ".join(sorted(missing_segments))
            )

        missing_tasks = [task for task, count in sorted(task_counts.items()) if count == 0]
        if missing_tasks:
            errors.append(
                "beta gate missing usability task evidence: "
                + ", ".join(missing_tasks)
            )

        if open_blockers:
            errors.append(
                "beta gate has unresolved P0/P1 finding(s): "
                + ", ".join(open_blockers)
            )

        if decision.get("status") != "GO":
            errors.append("beta gate requires explicit human decision.status=GO")
        if not decision.get("reviewedAt"):
            errors.append("beta gate requires decision.reviewedAt")
        rationale = decision.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append("beta gate requires a non-empty decision.rationale")

    return errors


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BetaResearchError("top-level document must be an object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="research/beta-sessions.json",
        help="Anonymized beta usability evidence JSON",
    )
    parser.add_argument(
        "--require-gate",
        action="store_true",
        help="Require all human-evidence conditions needed to release Beta",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Copy research/beta-sessions.example.json "
            "and replace example data with anonymized real sessions."
        )

    try:
        payload = load(path)
    except (OSError, json.JSONDecodeError, BetaResearchError) as exc:
        raise SystemExit(f"Invalid beta research file: {exc}") from exc

    errors = validate_document(payload, require_gate=args.require_gate)
    if errors:
        raise SystemExit("\n".join(f"- {error}" for error in errors))

    mode = "release gate" if args.require_gate else "structure"
    print(f"OK beta research {mode}: {path}")


if __name__ == "__main__":
    main()
