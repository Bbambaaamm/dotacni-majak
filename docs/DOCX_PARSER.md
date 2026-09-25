# DOCX Parsing

Issue #236 implements deterministic extraction from Office Open XML DOCX.

## Security boundary

Before python-docx receives the bytes, `inspect_document()` validates:

- file size,
- ZIP/OpenXML signature,
- archive entry count and sizes,
- compression-ratio limits,
- unsafe archive paths,
- encrypted ZIP entries,
- XML DTD/entity declarations.

## Provenance

Blocks retain document order and stable parser-local anchors:

- headings: `docx.heading.N`
- paragraphs: `docx.p.N`
- tables: `docx.table.N`

Heading blocks maintain `section_path`; following paragraphs/tables inherit
the current section path.

Tables preserve the logical grid returned by python-docx. The parser does not
attempt to invent semantic meaning for merged cells.

## External links

Only external HTTP(S) hyperlink relationship targets without URL credentials
are retained as metadata. They are sorted/deduplicated and are **never fetched**
by the document parser.

Network access remains exclusively in Source Adapters through GuardedHttpClient.

## Failure behavior

Corrupt/unsafe OpenXML fails closed. Resource limits cover input size, blocks,
total text, paragraph size, table-cell count and external-link count.
