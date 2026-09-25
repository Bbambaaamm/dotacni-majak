import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.document_model import BlockKind
from dotacni_majak_ingestion.html_parser import (
    HtmlDocumentError,
    HtmlParserPolicy,
    parse_html_document,
)


FIXTURE = ROOT / "tests" / "fixtures" / "html" / "sample_grant.html"


class HtmlParserTest(unittest.TestCase):
    def test_extracts_structure_and_excludes_script_style(self):
        parsed = parse_html_document(
            FIXTURE.read_bytes(),
            base_url="https://nsa.gov.cz/vyzva/",
        )
        self.assertEqual(parsed.format, "HTML")
        self.assertIn("Regiony 2026", parsed.canonical_text)
        self.assertIn("sportovní infrastruktury", parsed.canonical_text)
        self.assertNotIn("NEZAHRNOUT", parsed.canonical_text)
        headings = [b for b in parsed.blocks if b.kind == BlockKind.HEADING]
        self.assertEqual(headings[0].heading_level, 1)
        self.assertEqual(headings[0].anchor.section_path, ("Regiony 2026",))
        self.assertEqual(
            headings[1].anchor.section_path,
            ("Regiony 2026", "Oprávnění žadatelé"),
        )

    def test_extracts_table_with_stable_anchor(self):
        parsed = parse_html_document(FIXTURE.read_bytes())
        tables = [b for b in parsed.blocks if b.kind == BlockKind.TABLE]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].anchor.locator, "html.table.1")
        self.assertEqual(tables[0].table_rows[1], ("Max. podpora", "90 %"))

    def test_resolves_safe_links_and_rejects_javascript(self):
        parsed = parse_html_document(
            FIXTURE.read_bytes(),
            base_url="https://nsa.gov.cz/vyzva/",
        )
        links = [b for b in parsed.blocks if b.kind == BlockKind.LINK]
        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].link_url,
            "https://nsa.gov.cz/dokumenty/podminky.pdf",
        )

    def test_enforces_input_and_block_limits(self):
        with self.assertRaises(HtmlDocumentError):
            parse_html_document(
                b"<p>too large</p>",
                policy=HtmlParserPolicy(max_input_bytes=5),
            )
        with self.assertRaises(HtmlDocumentError):
            parse_html_document(
                "<p>a</p><p>b</p>",
                policy=HtmlParserPolicy(max_blocks=1),
            )


if __name__ == "__main__":
    unittest.main()
