# PDF Text Parsing

Issue #235 implements deterministic text extraction for text-based PDFs.

## Provenance model

The parser emits at most one text block per PDF page.

Each non-empty page uses a stable 1-based anchor:

- `pdf.page.1`
- `pdf.page.2`
- ...

The anchor also sets `SourceAnchor.page` to the same page number. This keeps
later `field_evidence.page_from/page_to` mapping explicit and avoids heuristic
paragraph boundaries.

## OCR policy

OCR is **not** performed by the PDF text parser.

If the PDF has no usable extracted text, the parser returns:

- no text blocks,
- `usable_text_layer=false`,
- `ocr_decision=FALLBACK_ALLOWED`,
- warning `OCR_FALLBACK_RECOMMENDED`.

The separate OCR fallback issue may then decide whether OCR is allowed.

## Failure behavior

- encrypted PDF → explicit `PdfEncryptedError`,
- corrupt/invalid PDF → `PdfDocumentError`,
- extraction failure on any page → explicit page-scoped error,
- page/input/text limits → safe failure, no partial canonical publication.

The document security layer validates the PDF signature and input size before
the PDF library receives the bytes.
