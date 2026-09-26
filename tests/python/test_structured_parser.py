import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.document_security import DocumentSecurityError
from dotacni_majak_ingestion.structured_parser import (
    StructuredDocumentError,
    StructuredParserPolicy,
    parse_json_document,
    parse_xml_document,
)


class StructuredParserTest(unittest.TestCase):
    def test_json_uses_stable_json_pointer_paths_and_sorted_canonical_text(self):
        parsed = parse_json_document(
            b'{"z":2,"calls":[{"deadline":"2026-10-01","rate":90}],"a":1}'
        )
        paths = {block.anchor.field_path: block.text for block in parsed.blocks}
        self.assertEqual(paths["/calls/0/deadline"], "2026-10-01")
        self.assertEqual(paths["/calls/0/rate"], "90")
        self.assertEqual(paths["/a"], "1")
        self.assertEqual(paths["/z"], "2")
        self.assertEqual(
            parsed.canonical_text,
            '{"a":1,"calls":[{"deadline":"2026-10-01","rate":90}],"z":2}',
        )
        self.assertEqual(parsed.metadata["canonical_serialization"], "JSON_SORTED_KEYS_COMPACT")

    def test_json_pointer_escapes_special_property_names(self):
        parsed = parse_json_document(b'{"a/b":{"x~y":"ok"}}')
        self.assertEqual(
            parsed.blocks[0].anchor.field_path,
            "/a~1b/x~0y",
        )

    def test_json_duplicate_keys_and_nonfinite_numbers_fail_closed(self):
        with self.assertRaises(StructuredDocumentError):
            parse_json_document(b'{"a":1,"a":2}')
        with self.assertRaises(StructuredDocumentError):
            parse_json_document(b'{"a":NaN}')

    def test_json_depth_limit_is_enforced(self):
        with self.assertRaises(StructuredDocumentError):
            parse_json_document(
                b'{"a":{"b":{"c":1}}}',
                policy=StructuredParserPolicy(max_depth=1),
            )

    def test_xml_emits_text_attributes_and_repeated_sibling_paths(self):
        parsed = parse_xml_document(
            b'<calls source="official"><call id="1"><deadline>2026-10-01</deadline></call>'
            b'<call id="2"><deadline>2026-11-01</deadline></call></calls>'
        )
        paths = {block.anchor.field_path: block.text for block in parsed.blocks}
        self.assertEqual(paths["/calls[1]/@source"], "official")
        self.assertEqual(paths["/calls[1]/call[1]/@id"], "1")
        self.assertEqual(
            paths["/calls[1]/call[1]/deadline[1]/#text"],
            "2026-10-01",
        )
        self.assertEqual(
            paths["/calls[1]/call[2]/deadline[1]/#text"],
            "2026-11-01",
        )
        self.assertEqual(parsed.metadata["canonical_serialization"], "XML_C14N2")

    def test_xml_xxe_and_dtd_fail_closed(self):
        dangerous = (
            b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<root>&xxe;</root>'
        )
        with self.assertRaises(DocumentSecurityError):
            parse_xml_document(dangerous)

    def test_xml_node_and_attribute_limits_are_enforced(self):
        with self.assertRaises(StructuredDocumentError):
            parse_xml_document(
                b'<root><a><b>1</b></a></root>',
                policy=StructuredParserPolicy(max_nodes=2),
            )
        with self.assertRaises(StructuredDocumentError):
            parse_xml_document(
                b'<root a="1" b="2"/>',
                policy=StructuredParserPolicy(max_attributes_per_element=1),
            )


if __name__ == "__main__":
    unittest.main()
