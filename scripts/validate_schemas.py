import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    schema_paths = sorted((root / "schemas").glob("v*/**/*.schema.json"))
    if not schema_paths:
        raise SystemExit("No canonical schemas found.")

    for path in schema_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {"$schema", "$id", "title", "type"}
        missing = required.difference(payload)
        if missing:
            raise SystemExit(f"{path}: missing required schema metadata: {sorted(missing)}")
        if payload["type"] != "object":
            raise SystemExit(f"{path}: top-level schema type must be object")
        print(f"OK {path.relative_to(root)}")


if __name__ == "__main__":
    main()
