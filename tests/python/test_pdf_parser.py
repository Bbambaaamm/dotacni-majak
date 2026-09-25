import io
import sys
import unittest
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.pdf_parser import (
    PdfDocumentError,
    PdfEncryptedError,
    PdfParserPolicy,
    parse_pdf_document,
)


def _pdf_with_pages(texts: list[str], *, metadata: dict[str, str] | None = None) -> bytes:
    writer = PdfWriter()

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)

    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )

        stream = StreamObject()
        escaped = (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .encode("latin-1", errors="replace")
        )
        stream.set_data(
            b"BT /F1 12 Tf 72 720 Td (" + escaped + b") Tj ET"
        )
        page[NameObject("/Contents")] = writer._add_object(stream)

    if metadata:
        writer.add_metadata(metadata)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class PdfParserTest(unittest.TestCase):
    def test_extracts_page_text_with_page_level_provenance(self):
        parsed = parse_pdf_document(
            _pdf_with_pages(
                ["Prvni strana", "Druha strana"],
                metadata={"/Title": "Test grant"},
            )
        )

        self.assertEqual(parsed.format, "PDF")
        self.assertEqual(len(parsed.blocks), 2)
        self.assertEqual(parsed.blocks[0].anchor.locator, "pdf.page.1")
        self.assertEqual(parsed.blocks[0].anchor.page, 1)
        self.assertEqual(parsed.blocks[1].anchor.locator, "pdf.page.2")
        self.assertEqual(parsed.blocks[1].anchor.page, 2)
        self.assertIn("Prvni strana", parsed.canonical_text)
        self.assertIn("Druha strana", parsed.canonical_text)
        self.assertTrue(parsed.metadata["usable_text_layer"])
        self.assertEqual(parsed.metadata["ocr_decision"], "NOT_NEEDED")
        self.assertEqual(parsed.metadata["pdf_metadata"]["Title"], "Test grant")

    def test_blank_pdf_requests_ocr_fallback_but_does_not_run_ocr(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buffer = io.BytesIO()
        writer.write(buffer)

        parsed = parse_pdf_document(buffer.getvalue())
        self.assertEqual(parsed.blocks, ())
        self.assertFalse(parsed.metadata["usable_text_layer"])
        self.assertEqual(parsed.metadata["ocr_decision"], "FALLBACK_ALLOWED")
        self.assertIn("OCR_FALLBACK_RECOMMENDED", parsed.warnings)

    def test_rejects_encrypted_pdf_explicitly(self):
        with self.assertRaises(PdfEncryptedError):
            parse_pdf_document(_encrypted_pdf())

    def test_rejects_corrupt_pdf(self):
        with self.assertRaises(PdfDocumentError):
            parse_pdf_document(b"%PDF-1.7\nthis is not a valid PDF")

    def test_enforces_page_limit(self):
        with self.assertRaises(PdfDocumentError):
            parse_pdf_document(
                _pdf_with_pages(["one", "two"]),
                policy=PdfParserPolicy(max_pages=1),
            )

    def test_enforces_total_text_limit(self):
        with self.assertRaises(PdfDocumentError):
            parse_pdf_document(
                _pdf_with_pages(["1234567890"]),
                policy=PdfParserPolicy(max_total_text_characters=5),
            )


if __name__ == "__main__":
    unittest.main()
