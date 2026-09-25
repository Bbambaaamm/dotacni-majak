from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from .document_model import BlockKind, ParsedBlock, ParsedDocument, SourceAnchor
from .document_security import DocumentSecurityPolicy, inspect_document


class DocxDocumentError(ValueError):
    pass


class DocxDependencyMissingError(DocxDocumentError):
    pass


@dataclass(frozen=True, slots=True)
class DocxParserPolicy:
    max_input_bytes: int = 50 * 1024 * 1024
    max_blocks: int = 20_000
    max_text_characters: int = 2_000_000
    max_paragraph_characters: int = 250_000
    max_table_cells: int = 50_000
    max_external_links: int = 5_000

    def __post_init__(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_blocks", self.max_blocks),
            ("max_text_characters", self.max_text_characters),
            ("max_paragraph_characters", self.max_paragraph_characters),
            ("max_table_cells", self.max_table_cells),
            ("max_external_links", self.max_external_links),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1")


_WS = re.compile(r"\s+")
_HEADING_NAME = re.compile(r"^heading\s*([1-6])$", re.IGNORECASE)
_HEADING_ID = re.compile(r"^heading([1-6])$", re.IGNORECASE)


def _clean(value: str) -> str:
    return _WS.sub(" ", value.replace("\x00", " ")).strip()


def _heading_level(paragraph) -> int | None:
    style = getattr(paragraph, "style", None)
    if style is None:
        return None

    for candidate in (
        getattr(style, "style_id", None),
        getattr(style, "name", None),
    ):
        if not candidate:
            continue
        value = str(candidate).strip()
        match = _HEADING_ID.match(value) or _HEADING_NAME.match(value)
        if match:
            return int(match.group(1))
    return None


def _iter_body_blocks(document) -> Iterable[object]:
    try:
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise DocxDependencyMissingError(
            "DOCX parsing requires the ingestion 'documents' optional dependencies"
        ) from exc

    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _external_links(document, *, limit: int) -> tuple[str, ...]:
    try:
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
    except ImportError as exc:
        raise DocxDependencyMissingError(
            "DOCX parsing requires the ingestion 'documents' optional dependencies"
        ) from exc

    links: set[str] = set()
    for relationship in document.part.rels.values():
        if relationship.reltype != RT.HYPERLINK or not relationship.is_external:
            continue
        target = str(relationship.target_ref).strip()
        parsed = urlsplit(target)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            continue
        links.add(target)
        if len(links) > limit:
            raise DocxDocumentError("DOCX external link limit exceeded")
    return tuple(sorted(links))


def parse_docx_document(
    content: bytes,
    *,
    policy: DocxParserPolicy | None = None,
) -> ParsedDocument:
    """Extract deterministic structure from a DOCX without following links."""

    policy = policy or DocxParserPolicy()
    inspect_document(
        content,
        declared_mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        policy=DocumentSecurityPolicy(max_file_bytes=policy.max_input_bytes),
    )

    try:
        from docx import Document
        from docx.opc.exceptions import PackageNotFoundError
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise DocxDependencyMissingError(
            "DOCX parsing requires the ingestion 'documents' optional dependencies"
        ) from exc

    try:
        document = Document(io.BytesIO(content))
    except (PackageNotFoundError, ValueError, KeyError) as exc:
        raise DocxDocumentError("invalid or corrupt DOCX") from exc
    except Exception as exc:
        raise DocxDocumentError("failed to open DOCX") from exc

    blocks: list[ParsedBlock] = []
    section_path: list[str] = []
    heading_count = 0
    paragraph_count = 0
    table_count = 0
    table_cells = 0
    text_characters = 0

    def append(block: ParsedBlock) -> None:
        nonlocal text_characters
        if len(blocks) >= policy.max_blocks:
            raise DocxDocumentError("DOCX block limit exceeded")
        text_characters += len(block.text)
        if text_characters > policy.max_text_characters:
            raise DocxDocumentError("DOCX extracted text limit exceeded")
        blocks.append(block)

    try:
        for block in _iter_body_blocks(document):
            if isinstance(block, Paragraph):
                text = _clean(block.text)
                if not text:
                    continue
                if len(text) > policy.max_paragraph_characters:
                    raise DocxDocumentError("DOCX paragraph text limit exceeded")

                level = _heading_level(block)
                if level is not None:
                    while len(section_path) >= level:
                        section_path.pop()
                    while len(section_path) < level - 1:
                        section_path.append("")
                    section_path.append(text)
                    heading_count += 1
                    append(
                        ParsedBlock(
                            kind=BlockKind.HEADING,
                            text=text,
                            heading_level=level,
                            anchor=SourceAnchor(
                                locator=f"docx.heading.{heading_count}",
                                section_path=tuple(section_path),
                            ),
                        )
                    )
                    continue

                paragraph_count += 1
                append(
                    ParsedBlock(
                        kind=BlockKind.PARAGRAPH,
                        text=text,
                        anchor=SourceAnchor(
                            locator=f"docx.p.{paragraph_count}",
                            section_path=tuple(section_path),
                        ),
                    )
                )
                continue

            if isinstance(block, Table):
                table_count += 1
                rows: list[tuple[str, ...]] = []
                for row in block.rows:
                    cells = tuple(_clean(cell.text) for cell in row.cells)
                    table_cells += len(cells)
                    if table_cells > policy.max_table_cells:
                        raise DocxDocumentError("DOCX table cell limit exceeded")
                    if any(cells):
                        rows.append(cells)

                if rows:
                    frozen_rows = tuple(rows)
                    append(
                        ParsedBlock(
                            kind=BlockKind.TABLE,
                            text="\n".join(" | ".join(row) for row in frozen_rows),
                            table_rows=frozen_rows,
                            anchor=SourceAnchor(
                                locator=f"docx.table.{table_count}",
                                section_path=tuple(section_path),
                            ),
                        )
                    )
    except DocxDocumentError:
        raise
    except Exception as exc:
        raise DocxDocumentError("failed while extracting DOCX structure") from exc

    links = _external_links(document, limit=policy.max_external_links)

    metadata = {
        "headings": heading_count,
        "paragraphs": paragraph_count,
        "tables": table_count,
        "table_cells": table_cells,
        "external_links": links,
        "external_links_followed": False,
    }

    return ParsedDocument(
        format="DOCX",
        blocks=tuple(blocks),
        canonical_text="\n\n".join(block.text for block in blocks),
        metadata=metadata,
    )
