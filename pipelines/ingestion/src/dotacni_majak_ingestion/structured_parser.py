from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as StdET

from .document_model import BlockKind, ParsedBlock, ParsedDocument, SourceAnchor
from .document_security import DocumentSecurityPolicy, inspect_document


class StructuredDocumentError(ValueError):
    pass


class StructuredDependencyMissingError(StructuredDocumentError):
    pass


@dataclass(frozen=True, slots=True)
class StructuredParserPolicy:
    max_input_bytes: int = 50 * 1024 * 1024
    max_nodes: int = 250_000
    max_depth: int = 64
    max_scalar_characters: int = 250_000
    max_total_text_characters: int = 10_000_000
    max_attributes_per_element: int = 256

    def __post_init__(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_nodes", self.max_nodes),
            ("max_depth", self.max_depth),
            ("max_scalar_characters", self.max_scalar_characters),
            ("max_total_text_characters", self.max_total_text_characters),
            ("max_attributes_per_element", self.max_attributes_per_element),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1")


def _json_pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _json_pointer(parent: str, component: str) -> str:
    escaped = _json_pointer_escape(component)
    return f"{parent}/{escaped}" if parent else f"/{escaped}"


def _scalar_text(value: Any, *, max_chars: int) -> str:
    if value is None:
        text = "null"
    elif value is True:
        text = "true"
    elif value is False:
        text = "false"
    elif isinstance(value, str):
        text = value.replace("\x00", "")
    elif isinstance(value, (int, float)):
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    else:
        text = str(value)

    if len(text) > max_chars:
        raise StructuredDocumentError("structured scalar text limit exceeded")
    return text


def _duplicate_keys_error(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StructuredDocumentError(
                f"duplicate JSON object key is not allowed: {key!r}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise StructuredDocumentError(
        f"non-finite JSON numeric constant is not allowed: {value}"
    )


def parse_json_document(
    content: bytes,
    *,
    policy: StructuredParserPolicy | None = None,
) -> ParsedDocument:
    policy = policy or StructuredParserPolicy()
    inspect_document(
        content,
        declared_mime_type="application/json",
        policy=DocumentSecurityPolicy(max_file_bytes=policy.max_input_bytes),
    )

    try:
        source_text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StructuredDocumentError("JSON must be UTF-8") from exc

    try:
        value = json.loads(
            source_text,
            object_pairs_hook=_duplicate_keys_error,
            parse_constant=_reject_json_constant,
        )
    except StructuredDocumentError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise StructuredDocumentError("invalid JSON document") from exc

    blocks: list[ParsedBlock] = []
    state = {"nodes": 0, "text": 0, "max_depth": 0}

    def visit(node: Any, pointer: str, depth: int) -> None:
        if depth > policy.max_depth:
            raise StructuredDocumentError("JSON nesting depth limit exceeded")
        state["nodes"] += 1
        state["max_depth"] = max(state["max_depth"], depth)
        if state["nodes"] > policy.max_nodes:
            raise StructuredDocumentError("JSON node limit exceeded")

        if isinstance(node, dict):
            for key in sorted(node):
                visit(node[key], _json_pointer(pointer, str(key)), depth + 1)
            return

        if isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, _json_pointer(pointer, str(index)), depth + 1)
            return

        text = _scalar_text(
            node,
            max_chars=policy.max_scalar_characters,
        )
        state["text"] += len(text)
        if state["text"] > policy.max_total_text_characters:
            raise StructuredDocumentError(
                "JSON total scalar text limit exceeded"
            )

        field_path = pointer or "/"
        blocks.append(
            ParsedBlock(
                kind=BlockKind.PARAGRAPH,
                text=text,
                anchor=SourceAnchor(
                    locator=f"json:{field_path}",
                    field_path=field_path,
                ),
            )
        )

    visit(value, "", 0)

    try:
        canonical_text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StructuredDocumentError(
            "failed to canonicalize JSON"
        ) from exc

    return ParsedDocument(
        format="JSON",
        blocks=tuple(blocks),
        canonical_text=canonical_text,
        metadata={
            "root_type": type(value).__name__,
            "nodes": state["nodes"],
            "max_depth": state["max_depth"],
            "scalar_fields": len(blocks),
            "canonical_serialization": "JSON_SORTED_KEYS_COMPACT",
        },
    )


def _xml_component(tag: Any) -> str:
    value = str(tag)
    if not value:
        raise StructuredDocumentError("XML element tag is empty")
    return value


def _xml_child_paths(parent) -> list[tuple[Any, str]]:
    counts: dict[str, int] = {}
    result: list[tuple[Any, str]] = []
    for child in list(parent):
        component = _xml_component(child.tag)
        counts[component] = counts.get(component, 0) + 1
        result.append((child, f"{component}[{counts[component]}]"))
    return result


def _xml_scalar_block(
    *,
    blocks: list[ParsedBlock],
    text: str,
    field_path: str,
    locator_prefix: str,
    state: dict[str, int],
    policy: StructuredParserPolicy,
) -> None:
    text = text.replace("\x00", "").strip()
    if not text:
        return
    if len(text) > policy.max_scalar_characters:
        raise StructuredDocumentError("XML scalar text limit exceeded")
    state["text"] += len(text)
    if state["text"] > policy.max_total_text_characters:
        raise StructuredDocumentError("XML total scalar text limit exceeded")

    blocks.append(
        ParsedBlock(
            kind=BlockKind.PARAGRAPH,
            text=text,
            anchor=SourceAnchor(
                locator=f"{locator_prefix}:{field_path}",
                field_path=field_path,
            ),
        )
    )


def parse_xml_document(
    content: bytes,
    *,
    policy: StructuredParserPolicy | None = None,
) -> ParsedDocument:
    policy = policy or StructuredParserPolicy()
    inspect_document(
        content,
        declared_mime_type="application/xml",
        policy=DocumentSecurityPolicy(max_file_bytes=policy.max_input_bytes),
    )

    try:
        from defusedxml import ElementTree as DefusedET
        from defusedxml.common import DefusedXmlException
    except ImportError as exc:
        raise StructuredDependencyMissingError(
            "XML parsing requires the ingestion 'documents' optional dependencies"
        ) from exc

    try:
        root = DefusedET.fromstring(content)
    except DefusedXmlException as exc:
        raise StructuredDocumentError(
            "unsafe XML construct was rejected"
        ) from exc
    except StdET.ParseError as exc:
        raise StructuredDocumentError("invalid XML document") from exc
    except Exception as exc:
        raise StructuredDocumentError("failed to parse XML") from exc

    blocks: list[ParsedBlock] = []
    state = {"nodes": 0, "text": 0, "max_depth": 0}

    root_component = _xml_component(root.tag)
    root_path = f"/{root_component}[1]"

    def visit(element, path: str, depth: int) -> None:
        if depth > policy.max_depth:
            raise StructuredDocumentError("XML nesting depth limit exceeded")
        state["nodes"] += 1
        state["max_depth"] = max(state["max_depth"], depth)
        if state["nodes"] > policy.max_nodes:
            raise StructuredDocumentError("XML node limit exceeded")

        if len(element.attrib) > policy.max_attributes_per_element:
            raise StructuredDocumentError(
                "XML attribute count limit exceeded"
            )

        for name in sorted(element.attrib):
            attribute_path = f"{path}/@{name}"
            _xml_scalar_block(
                blocks=blocks,
                text=str(element.attrib[name]),
                field_path=attribute_path,
                locator_prefix="xml",
                state=state,
                policy=policy,
            )

        if element.text and element.text.strip():
            _xml_scalar_block(
                blocks=blocks,
                text=element.text,
                field_path=f"{path}/#text",
                locator_prefix="xml",
                state=state,
                policy=policy,
            )

        for child, component in _xml_child_paths(element):
            child_path = f"{path}/{component}"
            visit(child, child_path, depth + 1)
            if child.tail and child.tail.strip():
                _xml_scalar_block(
                    blocks=blocks,
                    text=child.tail,
                    field_path=f"{child_path}/#tail",
                    locator_prefix="xml",
                    state=state,
                    policy=policy,
                )

    visit(root, root_path, 0)

    try:
        xml_text = StdET.tostring(root, encoding="unicode")
        canonical_text = StdET.canonicalize(
            xml_data=xml_text,
            strip_text=False,
            with_comments=False,
        )
    except Exception as exc:
        raise StructuredDocumentError(
            "failed to canonicalize XML"
        ) from exc

    return ParsedDocument(
        format="XML",
        blocks=tuple(blocks),
        canonical_text=canonical_text,
        metadata={
            "root_tag": root_component,
            "nodes": state["nodes"],
            "max_depth": state["max_depth"],
            "scalar_fields": len(blocks),
            "canonical_serialization": "XML_C14N2",
        },
    )
