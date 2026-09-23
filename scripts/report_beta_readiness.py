from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "release" / "beta-gate.json"


def main() -> None:
    payload = json.loads(GATE.read_text(encoding="utf-8"))
    print(f"Gate: {payload['gate']} v{payload['version']}")
    print("\nAutomated evidence required:")
    for item in payload["automated"]:
        print(f"  - {item}")
    print("\nManual/human evidence required:")
    for item in payload["manual"]:
        print(f"  - {item}")
    print("\nRule:")
    print(f"  {payload['rule']}")
    print(
        "\nThis command reports the contract only; it deliberately does not "
        "pretend manual usability evidence exists."
    )


if __name__ == "__main__":
    main()
