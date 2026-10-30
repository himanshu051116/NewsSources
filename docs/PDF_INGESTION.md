# PDF ingestion: bounded native extraction + optional OCR

This feature is built on the `upgrade/v1.26-reliability` branch and is
reviewed independently in draft PR #2. It does not enable user uploads.

## Acquisition and safety

Discovered recent `.pdf` URLs pass the normal article freshness policy,
then use the existing SSRF-protected, robots-aware, size-limited HTTP fetcher.
Actual PDF signatures and MIME types are checked before extraction. A
publisher PDF response is **not** processed as HTML, and browser rendering
and HTML-specific fidelity analysis are skipped.

Native text extraction uses Poppler (`pdfinfo`, `pdftotext`). When enabled,
Tesseract OCR is used for pages with very little native text; `pdftoppm`
rasterizes these pages. All CLI calls use argument arrays, fixed subprocess
timeouts and temporary working directories, with limits on pages, bytes and
page output. Failed and missing OCR tools do not silently invent document text.

## Configuration

- `NEWSINTEL_PDF_MAX_PAGES=40` — at most this many PDF pages are extracted.
  The original page count and truncation warning are preserved.
- `NEWSINTEL_PDF_OCR_ENABLED=false` — OCR **off** by default. Set to
  `true` only if scanned PDF extraction is intentionally required.
- `NEWSINTEL_PDF_OCR_LANGUAGE=eng` — Tesseract language codes; use
  `eng+hin` when both OCR language packs are installed.
- `NEWSINTEL_FETCH_MAX_BYTES=8000000` — shared HTTP byte cap; PDF
  extraction also enforces this size.

The Docker image includes Poppler, Tesseract and English/Hindi language
packages. Linux CI installs the same conversion binaries. Windows native PDF
tests skip when the external programs are not installed.

## Evidence and provenance

Each article version stores `document_pages` in JSONB metadata, and the
article-version API exposes it. Every processed page includes its 1-based
page number, a `#page=N` URL, start/end character offsets into the
stored concatenated text, SHA-256 of page text, and extraction method.

OCR page records explicitly say `ocr_unverified=true`; they must be
human-reviewed before use as conclusive evidence. The pipeline does **not**
automatically attach PDF page citations to every extracted claim yet.

## Limits not yet solved

- Long or large documents beyond the configured cap are explicitly truncated.
- Extraction of tables, graphics, handwriting and complex multi-column layout
  is not fully reliable; validate against representative publisher PDFs.
- OCR confidence is not calibrated. It does not establish factual truth.
- Historical archive backfill and user-upload PDFs need separate admission
  and permissions flows.
- A page URL + text offset is provenance metadata, not a verified quotation or
  automatic claim-level evidence link.
