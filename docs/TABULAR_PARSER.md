# XLSX / CSV Parsing

Issue #237 implements deterministic parsing of official tabular exports.

## Row-level provenance

Each emitted non-empty row is one ParsedBlock with an original 1-based row
anchor:

- XLSX: `xlsx.sheet.1.row.7`
- CSV: `csv.row.7`

For XLSX the sheet name is also stored in `SourceAnchor.section_path`.

## Values

Values are converted to deterministic text:

- dates/datetimes/times → ISO-8601,
- booleans → TRUE/FALSE,
- finite numbers → stable decimal text,
- formulas → original formula text.

**Formulas are never evaluated.**

## Merged cells

Policy: `TOP_LEFT_ONLY`.

The top-left value is retained; merged child cells remain empty. Merged ranges
are exposed in metadata. The parser never invents repeated values.

## XLSX safety

Document security preflight checks ZIP/OpenXML limits and XXE markers before
openpyxl runs. External workbook links are disabled with `keep_links=False`.

## CSV encoding and delimiter

CSV prefers UTF-8/UTF-8 BOM and has an explicit CP1250 fallback. The fallback
is surfaced as a warning. Delimiter detection is constrained to comma,
semicolon, tab and pipe.
