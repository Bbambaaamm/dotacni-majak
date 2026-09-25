from __future__ import annotations

import io
import posixpath
import zipfile
from dataclasses import dataclass
from enum import Enum


class DocumentSecurityError(ValueError):
    pass


class DocumentKind(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"
    XLSX = "XLSX"
    CSV = "CSV"
    XML = "XML"
    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class DocumentSecurityPolicy:
    max_file_bytes: int = 50 * 1024 * 1024
    max_zip_entries: int = 5_000
    max_zip_total_uncompressed_bytes: int = 200 * 1024 * 1024
    max_zip_single_entry_bytes: int = 50 * 1024 * 1024
    max_zip_compression_ratio: float = 150.0

    def __post_init__(self) -> None:
        if self.max_file_bytes < 1:
            raise ValueError("max_file_bytes must be >= 1")
        if self.max_zip_entries < 1:
            raise ValueError("max_zip_entries must be >= 1")
        if self.max_zip_total_uncompressed_bytes < 1:
            raise ValueError("max_zip_total_uncompressed_bytes must be >= 1")
        if self.max_zip_single_entry_bytes < 1:
            raise ValueError("max_zip_single_entry_bytes must be >= 1")
        if self.max_zip_compression_ratio <= 1:
            raise ValueError("max_zip_compression_ratio must be > 1")


@dataclass(frozen=True, slots=True)
class InspectedDocument:
    kind: DocumentKind
    mime_type: str
    size_bytes: int
    archive_entries: int = 0
    uncompressed_bytes: int = 0


_MIME_TO_KIND = {
    "application/pdf": DocumentKind.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentKind.DOCX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentKind.XLSX,
    "text/csv": DocumentKind.CSV,
    "application/csv": DocumentKind.CSV,
    "application/xml": DocumentKind.XML,
    "text/xml": DocumentKind.XML,
    "text/plain": DocumentKind.TEXT,
}


def inspect_document(
    content: bytes,
    *,
    declared_mime_type: str,
    policy: DocumentSecurityPolicy | None = None,
) -> InspectedDocument:
    policy = policy or DocumentSecurityPolicy()

    if len(content) > policy.max_file_bytes:
        raise DocumentSecurityError(
            f"document exceeds max size: {len(content)} > {policy.max_file_bytes}"
        )

    mime = declared_mime_type.split(";", 1)[0].strip().lower()
    kind = _MIME_TO_KIND.get(mime)
    if kind is None:
        raise DocumentSecurityError(f"unsupported MIME type: {mime!r}")

    if kind is DocumentKind.PDF:
        if not content.startswith(b"%PDF-"):
            raise DocumentSecurityError("declared PDF does not have PDF signature")
        return InspectedDocument(kind, mime, len(content))

    if kind in {DocumentKind.DOCX, DocumentKind.XLSX}:
        return _inspect_openxml(content, kind=kind, mime=mime, policy=policy)

    if kind is DocumentKind.XML:
        _reject_xml_dtd_and_entities(content)
        return InspectedDocument(kind, mime, len(content))

    return InspectedDocument(kind, mime, len(content))


def _inspect_openxml(
    content: bytes,
    *,
    kind: DocumentKind,
    mime: str,
    policy: DocumentSecurityPolicy,
) -> InspectedDocument:
    if not content.startswith(b"PK"):
        raise DocumentSecurityError("declared OpenXML document is not a ZIP archive")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise DocumentSecurityError("invalid ZIP/OpenXML archive") from exc

    infos = archive.infolist()
    if len(infos) > policy.max_zip_entries:
        raise DocumentSecurityError(
            f"archive contains too many entries: {len(infos)}"
        )

    total = 0
    names = set()
    for info in infos:
        _validate_archive_name(info.filename)

        if info.flag_bits & 0x1:
            raise DocumentSecurityError(
                f"encrypted archive entry is not allowed: {info.filename!r}"
            )

        if info.filename in names:
            raise DocumentSecurityError(
                f"duplicate archive entry is not allowed: {info.filename!r}"
            )
        names.add(info.filename)

        if info.file_size > policy.max_zip_single_entry_bytes:
            raise DocumentSecurityError(
                f"archive entry too large: {info.filename!r}"
            )

        total += info.file_size
        if total > policy.max_zip_total_uncompressed_bytes:
            raise DocumentSecurityError(
                "archive total uncompressed size exceeds limit"
            )

        if info.file_size > 0:
            compressed = max(info.compress_size, 1)
            ratio = info.file_size / compressed
            if ratio > policy.max_zip_compression_ratio:
                raise DocumentSecurityError(
                    f"suspicious compression ratio for {info.filename!r}: {ratio:.1f}"
                )

    if "[Content_Types].xml" not in names:
        raise DocumentSecurityError("OpenXML archive misses [Content_Types].xml")

    required_prefix = "word/" if kind is DocumentKind.DOCX else "xl/"
    if not any(name.startswith(required_prefix) for name in names):
        raise DocumentSecurityError(
            f"archive does not contain expected {kind.value} structure"
        )

    # XML entries are inspected before any downstream XML parser sees them.
    for info in infos:
        if not info.filename.lower().endswith((".xml", ".rels")):
            continue
        with archive.open(info, "r") as handle:
            xml = handle.read(
                min(
                    info.file_size,
                    policy.max_zip_single_entry_bytes,
                )
            )
        _reject_xml_dtd_and_entities(xml)

    return InspectedDocument(
        kind=kind,
        mime_type=mime,
        size_bytes=len(content),
        archive_entries=len(infos),
        uncompressed_bytes=total,
    )


def _validate_archive_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise DocumentSecurityError(f"unsafe archive path: {name!r}")
    if "\x00" in normalized:
        raise DocumentSecurityError(f"NUL byte in archive path: {name!r}")

    collapsed = posixpath.normpath(normalized)
    if collapsed == ".." or collapsed.startswith("../"):
        raise DocumentSecurityError(f"path traversal in archive: {name!r}")


def _reject_xml_dtd_and_entities(content: bytes) -> None:
    probe = content.upper()
    if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
        raise DocumentSecurityError(
            "XML DTD/entity declarations are forbidden (XXE defense)"
        )


class OcrDecision(str, Enum):
    NOT_NEEDED = "NOT_NEEDED"
    FALLBACK_ALLOWED = "FALLBACK_ALLOWED"
    NOT_ALLOWED = "NOT_ALLOWED"


def ocr_decision(
    *,
    kind: DocumentKind,
    usable_text_layer: bool,
) -> OcrDecision:
    if usable_text_layer:
        return OcrDecision.NOT_NEEDED
    if kind is DocumentKind.PDF:
        return OcrDecision.FALLBACK_ALLOWED
    return OcrDecision.NOT_ALLOWED
