from __future__ import annotations

import argparse
import hashlib
import json
import keyword
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "v1"
DEFAULT_OUTPUT = ROOT / "packages" / "canonical-schema" / "generated"


def load_schemas() -> list[tuple[Path, dict[str, Any]]]:
    schemas = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        schemas.append((path, payload))
    if not schemas:
        raise SystemExit("No canonical schemas found.")
    return schemas


def ts_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    raise ValueError(f"unsupported TypeScript literal: {value!r}")


def py_literal(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)
    raise ValueError(f"unsupported Python literal: {value!r}")


def schema_types(schema: dict[str, Any]) -> tuple[list[str], bool]:
    raw = schema.get("type")
    if raw is None:
        return [], False
    values = [raw] if isinstance(raw, str) else list(raw)
    nullable = "null" in values
    return [value for value in values if value != "null"], nullable


def render_ts_type(schema: dict[str, Any]) -> str:
    if "const" in schema:
        return ts_literal(schema["const"])
    if "enum" in schema:
        return " | ".join(ts_literal(value) for value in schema["enum"])

    types, nullable = schema_types(schema)
    if not types:
        base = "unknown"
    else:
        rendered = []
        for value in types:
            if value == "string":
                rendered.append("string")
            elif value in {"integer", "number"}:
                rendered.append("number")
            elif value == "boolean":
                rendered.append("boolean")
            elif value == "array":
                item_type = render_ts_type(schema.get("items", {}))
                rendered.append(f"Array<{item_type}>")
            elif value == "object":
                rendered.append("Record<string, unknown>")
            else:
                raise ValueError(f"unsupported JSON Schema type: {value!r}")
        base = " | ".join(dict.fromkeys(rendered))

    if nullable:
        base += " | null"
    return base


def render_py_type(schema: dict[str, Any]) -> str:
    if "const" in schema:
        return f"Literal[{py_literal(schema['const'])}]"
    if "enum" in schema:
        literals = ", ".join(py_literal(value) for value in schema["enum"])
        return f"Literal[{literals}]"

    types, nullable = schema_types(schema)
    if not types:
        base = "Any"
    else:
        rendered = []
        for value in types:
            if value == "string":
                rendered.append("str")
            elif value == "integer":
                rendered.append("int")
            elif value == "number":
                rendered.append("float")
            elif value == "boolean":
                rendered.append("bool")
            elif value == "array":
                item_type = render_py_type(schema.get("items", {}))
                rendered.append(f"list[{item_type}]")
            elif value == "object":
                rendered.append("dict[str, Any]")
            else:
                raise ValueError(f"unsupported JSON Schema type: {value!r}")
        base = " | ".join(dict.fromkeys(rendered))

    if nullable:
        base += " | None"
    return base


def validate_python_field(name: str) -> None:
    if not name.isidentifier() or keyword.iskeyword(name):
        raise ValueError(
            f"canonical property {name!r} is not a valid Python identifier; "
            "add alias-generation support before using it"
        )


def render_typescript(schemas: list[tuple[Path, dict[str, Any]]]) -> str:
    lines = [
        "// GENERATED FILE — DO NOT EDIT.",
        "// Source: schemas/v1/*.schema.json",
        "",
    ]
    for _, schema in schemas:
        title = schema["title"]
        required = set(schema.get("required", []))
        lines.append(f"export interface {title} {{")
        for name, prop in schema.get("properties", {}).items():
            optional = "" if name in required else "?"
            lines.append(
                f"  {json.dumps(name)}{optional}: {render_ts_type(prop)};"
            )
        lines.append("}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_python(schemas: list[tuple[Path, dict[str, Any]]]) -> str:
    lines = [
        "# GENERATED FILE — DO NOT EDIT.",
        "# Source: schemas/v1/*.schema.json",
        "from __future__ import annotations",
        "",
        "from typing import Any, Literal",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "",
        "class UnsetType:",
        "    __slots__ = ()",
        "",
        "    def __repr__(self) -> str:",
        "        return 'UNSET'",
        "",
        "",
        "UNSET = UnsetType()",
        "",
    ]
    for _, schema in schemas:
        title = schema["title"]
        required = set(schema.get("required", []))
        lines.extend(
            [
                "",
                f"class {title}(BaseModel):",
                "    model_config = ConfigDict(",
                "        extra='forbid',",
                "        arbitrary_types_allowed=True,",
                "    )",
            ]
        )
        properties = schema.get("properties", {})
        if not properties:
            lines.append("    pass")
            continue
        for name, prop in properties.items():
            validate_python_field(name)
            type_hint = render_py_type(prop)
            if name in required:
                lines.append(f"    {name}: {type_hint}")
            else:
                lines.append(
                    f"    {name}: {type_hint} | UnsetType = UNSET"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_manifest(
    schemas: list[tuple[Path, dict[str, Any]]],
) -> str:
    entries = []
    for path, payload in schemas:
        raw = path.read_bytes()
        entries.append(
            {
                "file": path.name,
                "title": payload["title"],
                "id": payload["$id"],
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    manifest = {
        "generator": "scripts/generate_contracts.py",
        "schemaVersion": "1.0.0",
        "schemas": entries,
    }
    return json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def generate(output_root: Path) -> None:
    schemas = load_schemas()
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "types.ts").write_text(
        render_typescript(schemas),
        encoding="utf-8",
    )
    (output_root / "models.py").write_text(
        render_python(schemas),
        encoding="utf-8",
    )
    (output_root / "manifest.json").write_text(
        render_manifest(schemas),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()
    generate(args.output_root.resolve())


if __name__ == "__main__":
    main()
