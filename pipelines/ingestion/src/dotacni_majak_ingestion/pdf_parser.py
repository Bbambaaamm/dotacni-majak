from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from .document_model import BlockKind, ParsedBlock, ParsedDocument, SourceAnchor
from .document_security import (
    DocumentKind,
    DocumentSecurityPolicy,
    inspect_document,
    ocr_decision,
)


class PdfDocumentError(ValueError):
    pass


class PdfEncryptedError(PdfDocumentError):
    pass


class PdfDependencyMissingError(PdfDocumentError):
    pass


@dataclass(frozen=True, slots=True)
class PdfParserPolicy:
    max_input_bytes: int = 50 * 1024 * 1024
    max_pages: int = 2_000
    max_page_text_characters: int = 500_000
    max_total_text_characters: int = 5_000_000
    max_metadata_value_characters: int = 4_096

    def __post_init__(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_pages", self.max_pages),
            ("max_page_text_characters", self.max_page_text_characters),
            ("max_total_text_characters", self.max_total_text_characters),
            ("max_metadata_value_characters", self.max_metadata_value_characters),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1")


_SPACE = re.compile(r"[ \t\f\v]+")


def _normalize_page_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [_SPACE.sub(" ", line).strip() for line in value.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    normalized: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if normalized and not blank:
                normalized.append("")
            blank = True
            continue
        normalized.append(line)
        blank = False
    return "\n".join(normalized).strip()


def _safe_metadata(metadata: Any, *, max_value_chars: int) -> dict[str, str]:
    if not metadata:
        return {}

    result: dict[str, str] = {}
    try:
        items = metadata.items()
    except AttributeError:
        return result

    for key, value in items:
        if value is None:
            continue
        name = str(key).lstrip("/")[:128]
        if not name:
            continue
        text = str(value).replace("\x00", "").strip()
        if not text:
            continue
        result[name] = text[:max_value_chars]
    return result


def parse_pdf_document(
    content: bytes,
    *,
    policy: PdfParserPolicy | None = None,
) -> ParsedDocument:
    """Extract text from a text-based PDF with page-level provenance.

    OCR is intentionally not performed here. Image-only/scanned PDFs return a
    valid ParsedDocument with no text blocks and an explicit
    OCR_FALLBACK_RECOMMENDED warning/metadata decision.
    """

    policy = policy or PdfParserPolicy()
    inspect_document(
        content,
        declared_mime_type="application/pdf",
        policy=DocumentSecurityPolicy(max_file_bytes=policy.max_input_bytes),
    )

    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise PdfDependencyMissingError(
            "PDF parsing requires the ingestion 'documents' optional dependencies"
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
    except (PdfReadError, ValueError, TypeError, OSError) as exc:
        raise PdfDocumentError("invalid or corrupt PDF") from exc
    except Exception as exc:
        raise PdfDocumentError("failed to open PDF") from exc

    try:
        if reader.is_encrypted:
            raise PdfEncryptedError("encrypted PDFs are not parsed automatically")

        page_count = len(reader.pages)
    except PdfEncryptedError:
        raise
    except Exception as exc:
        raise PdfDocumentError("failed to inspect PDF structure") from exc

    if page_count > policy.max_pages:
        raise PdfDocumentError(
            f"PDF page limit exceeded: {page_count} > {policy.max_pages}"
        )

    blocks: list[ParsedBlock] = []
    total_text_chars = 0
    empty_pages: list[int] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw_text = page.extract_text() or ""
        except Exception as exc:
            raise PdfDocumentError(
                f"failed to extract text from PDF page {page_number}"
            ) from exc

        text = _normalize_page_text(raw_text)
        if len(text) > policy.max_page_text_characters:
            raise PdfDocumentError(
                f"PDF page {page_number} text limit exceeded: "
                f"{len(text)} > {policy.max_page_text_characters}"
            )

        if not text:
            empty_pages.append(page_number)
            continue

        total_text_chars += len(text)
        if total_text_chars > policy.max_total_text_characters:
            raise PdfDocumentError(
                "PDF total extracted text exceeds configured limit"
            )

        blocks.append(
            ParsedBlock(
                kind=BlockKind.PARAGRAPH,
                text=text,
                anchor=SourceAnchor(
                    locator=f"pdf.page.{page_number}",
                    page=page_number,
                ),
            )
        )

    usable_text_layer = bool(blocks)
    ocr = ocr_decision(
        kind=DocumentKind.PDF,
        usable_text_layer=usable_text_layer,
    )

    warnings: list[str] = []
    if not usable_text_layer:
        warnings.append("OCR_FALLBACK_RECOMMENDED")
    elif empty_pages:
        warnings.append(f"EMPTY_TEXT_PAGES:{len(empty_pages)}")

    metadata = {
        "pages": page_count,
        "text_pages": len(blocks),
        "empty_text_pages": tuple(empty_pages),
        "usable_text_layer": usable_text_layer,
        "ocr_decision": ocr.value,
        "pdf_metadata": _safe_metadata(
            reader.metadata,
            max_value_chars=policy.max_metadata_value_characters,
        ),
    }

    return ParsedDocument(
        format="PDF",
        blocks=tuple(blocks),
        canonical_text="\n\n".join(block.text for block in blocks),
        metadata=metadata,
        warnings=tuple(warnings),
    )
