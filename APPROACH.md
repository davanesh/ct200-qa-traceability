# Approach and decision log

## Pipeline and hierarchy

The supplied documents are born-digital PDFs with a selectable text layer, so PyMuPDF extracts sorted text blocks without OCR loss. OCR is not run unnecessarily; a scanned page with no text would require OCR and currently is surfaced as unsupported via missing headings. Numbered heading prefixes drive tree structure. Dotted depth is retained as `level`; when numbering skips levels (for example `2.1.1.1` directly after `2.1`), the node keeps its explicit depth and parents to the nearest existing numeric prefix. This avoids inventing absent sections. Out-of-order `3.4` and `3.3` remain in source order under section 3. Duplicate headings remain separate nodes with unique IDs. Paragraphs and table-like text remain in node body; the PDF extractor preserves text but this implementation does not infer table cells or figure captions reliably.

## Data and version matching

SQLAlchemy/SQLite stores document versions, nodes, selections, and generations. Generation JSON plus exact input snapshots are stored in SQLite rather than adding MongoDB: this keeps the assignment reproducible with one local database while retaining document-shaped output. Every node has an immutable ID, logical ID, parent, level, body and SHA-256 content hash. Across versions, matching currently uses heading and occurrence order (a pragmatic title match); changed body keeps the logical ID and gets a different content hash. Renames, duplicated headings reordered between versions, and identical headings under different parents can be mis-matched; production matching should use a canonical structural path plus explicit ambiguity review.

## LLM contract and failure policy

Generation sends only selected, version-pinned source text. The prompt requires 3–5 executable tests with steps, observable expected result and source node. The caller must configure an OpenAI-compatible endpoint or Groq. We parse JSON and validate required keys and count before persistence; malformed or incomplete output fails the request with a gateway error and is not stored. Repeated submission creates a new generation, preserving an audit trail instead of silently replacing prior output. Automatic retries are omitted to avoid hiding provider failures and duplicate cost; schema-constrained JSON is requested where supported.

## Known structural edge cases

- The text contains numbering gaps (`2.1.1.1`) and out-of-order numbered headings (`3.4` before `3.3`).
- Body text includes table rows without reliable cell separators; table reconstruction is lossy.
- Soft hyphens/ligatures and line wraps can vary by PDF extraction; hashes are byte-sensitive after extraction.
- A PDF with image-only pages needs OCR, which is not currently integrated.
- Some leading title lines are not numbered, so the current parser focuses on numbered sections and does not create a document-title node.

## Validation and iteration

The two PDFs were manually inspected through extracted text. Comparison exposes body changes in battery life, cuff inflation increment, error code behavior, alarm coverage, and a new export section. The hierarchy strategy is intentionally conservative about numbering gaps and preserves source ordering. The initial approach of assuming sequential section numbers would have lost `2.1.1.1` and incorrectly ordered 3.3/3.4; prefix-parent resolution and source ordinals address those cases. See parser tests for repeatable checks of those behaviors.

## Decision log

1. **Most likely silent error:** text extraction can preserve wording yet attach it to the wrong heading, particularly near page breaks and tables. I would catch this with page-by-page visual comparisons and sampled source-to-node checks before approving an ingest.
2. **Simplicity chosen:** heading-based matching and local SQLite JSON storage favor an inspectable assignment-sized system. Reordered duplicate headings would be matched incorrectly first; production should require ambiguity resolution and use MongoDB or another document store if generated records need independent scaling.
3. **Unsupported input:** image-only/scanned PDF pages are not OCRed. Ingestion fails when no numbered headings are found rather than silently creating an empty document; mixed image/text pages may still omit image-only content and need page-level OCR detection.

## More time

Add page provenance and bounding boxes, OCR fallback for pages with no text, table and caption extraction, explicit ambiguity reports for version matching, schema validation with retry limits, and integration tests against representative parser fixtures.
