import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.document_security import (
    DocumentKind,
    DocumentSecurityError,
    DocumentSecurityPolicy,
    OcrDecision,
    inspect_document,
    ocr_decision,
)


def zip_bytes(entries: dict[str, bytes], *, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


class DocumentSecurityTest(unittest.TestCase):
    def test_valid_pdf_signature(self):
        inspected = inspect_document(
            b"%PDF-1.7\n%%EOF",
            declared_mime_type="application/pdf",
        )
        self.assertEqual(inspected.kind, DocumentKind.PDF)

    def test_declared_pdf_with_wrong_signature_is_rejected(self):
        with self.assertRaises(DocumentSecurityError):
            inspect_document(
                b"<html>not pdf</html>",
                declared_mime_type="application/pdf",
            )

    def test_csv_is_recognized_as_plain_tabular_document(self):
        inspected = inspect_document(
            b"name;value\nTest;1\n",
            declared_mime_type="text/csv",
        )
        self.assertEqual(inspected.kind, DocumentKind.CSV)

    def test_json_is_recognized_as_structured_document(self):
        inspected = inspect_document(
            b'{"ok": true}',
            declared_mime_type="application/json",
        )
        self.assertEqual(inspected.kind, DocumentKind.JSON)

    def test_oversized_document_is_rejected_before_parsing(self):
        with self.assertRaises(DocumentSecurityError):
            inspect_document(
                b"x" * 11,
                declared_mime_type="text/plain",
                policy=DocumentSecurityPolicy(max_file_bytes=10),
            )

    def test_docx_path_traversal_is_rejected(self):
        payload = zip_bytes(
            {
                "[Content_Types].xml": b"<Types/>",
                "word/document.xml": b"<document/>",
                "../escape.xml": b"<x/>",
            }
        )
        with self.assertRaises(DocumentSecurityError):
            inspect_document(
                payload,
                declared_mime_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            )

    def test_xxe_doctype_is_rejected_in_openxml(self):
        payload = zip_bytes(
            {
                "[Content_Types].xml": b"<Types/>",
                "word/document.xml": (
                    b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
                    b"<document>&xxe;</document>"
                ),
            }
        )
        with self.assertRaises(DocumentSecurityError):
            inspect_document(
                payload,
                declared_mime_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            )

    def test_suspicious_compression_ratio_is_rejected(self):
        payload = zip_bytes(
            {
                "[Content_Types].xml": b"<Types/>",
                "xl/workbook.xml": b"A" * 20_000,
            }
        )
        with self.assertRaises(DocumentSecurityError):
            inspect_document(
                payload,
                declared_mime_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                policy=DocumentSecurityPolicy(max_zip_compression_ratio=5),
            )

    def test_ocr_is_only_fallback_for_pdf_without_text_layer(self):
        self.assertEqual(
            ocr_decision(kind=DocumentKind.PDF, usable_text_layer=True),
            OcrDecision.NOT_NEEDED,
        )
        self.assertEqual(
            ocr_decision(kind=DocumentKind.PDF, usable_text_layer=False),
            OcrDecision.FALLBACK_ALLOWED,
        )
        self.assertEqual(
            ocr_decision(kind=DocumentKind.DOCX, usable_text_layer=False),
            OcrDecision.NOT_ALLOWED,
        )


if __name__ == "__main__":
    unittest.main()
