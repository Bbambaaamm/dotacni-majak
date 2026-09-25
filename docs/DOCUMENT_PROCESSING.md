# Document Processing

## Common parser representation

Document parsers return ParsedDocument with ordered ParsedBlock entries.

Each block carries a SourceAnchor suitable for later provenance:
- locator — deterministic parser-local location,
- optional page,
- section path,
- row/cell,
- field path.

The common representation is internal processing data, not a replacement for
the canonical GrantCall/DocumentVersion schema.

## HTML

parse_html_document() is deterministic and does not execute or fetch content.

It:
- excludes script/style/noscript/template/svg content,
- extracts headings, paragraphs, list items, tables and safe links,
- resolves relative HTTP(S) links only as metadata,
- preserves heading hierarchy in section_path,
- emits stable anchors such as html.heading.1 or html.table.1,
- enforces input, block, text and table-cell limits.

Links using javascript/data/mailto/fragments are not emitted as document links.
The parser never follows links; network retrieval remains exclusively inside
the guarded Source Adapter layer.
