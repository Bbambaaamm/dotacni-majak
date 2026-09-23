import json
from pathlib import Path


CANONICAL_VERSION = "1.0.0"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    schema_paths = sorted((root / "schemas").glob("v*/**/*.schema.json"))
    if not schema_paths:
        raise SystemExit("No canonical schemas found.")

    seen_ids: set[str] = set()

    for path in schema_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {"$schema", "$id", "title", "type", "properties"}
        missing = required.difference(payload)
        if missing:
            raise SystemExit(f"{path}: missing required schema metadata: {sorted(missing)}")

        if payload["type"] != "object":
            raise SystemExit(f"{path}: top-level schema type must be object")

        if payload.get("additionalProperties") is not False:
            raise SystemExit(f"{path}: top-level canonical object must set additionalProperties=false")

        schema_id = payload["$id"]
        if schema_id in seen_ids:
            raise SystemExit(f"{path}: duplicate $id {schema_id}")
        seen_ids.add(schema_id)

        schema_version = payload["properties"].get("schemaVersion", {})
        if schema_version.get("const") != CANONICAL_VERSION:
            raise SystemExit(
                f"{path}: schemaVersion const must be {CANONICAL_VERSION}, "
                f"got {schema_version.get('const')!r}"
            )

        required_fields = payload.get("required", [])
        if "schemaVersion" not in required_fields:
            raise SystemExit(f"{path}: schemaVersion must be required")

        print(f"OK {path.relative_to(root)}")


if __name__ == "__main__":
    main()
