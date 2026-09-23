from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "release" / "v1-gate.json"


def main() -> None:
    payload = json.loads(GATE.read_text(encoding="utf-8"))
    print(f"Gate: {payload['gate']} v{payload['version']}")
    print(f"Depends on: {', '.join(payload['dependsOn'])}")
    print("\nAutomated evidence required:")
    for item in payload["automated"]:
        print(f"  - {item}")
    print("\nManual/review evidence required:")
    for item in payload["manual"]:
        print(f"  - {item}")
    print("\nRelease record must include:")
    for item in payload["releaseEvidence"]:
        print(f"  - {item}")
    print("\nThis is a release contract, not evidence that the gate has passed.")


if __name__ == "__main__":
    main()
