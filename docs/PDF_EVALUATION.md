# PDF ingestion: consolidated validation and release gate

This document is the offline, reproducible QA procedure for
[PDF/OCR ingestion](PDF_INGESTION.md) in draft PR #2.

## How to evaluate real documents

1. Put PDFs on the evaluation machine; do not commit copyrighted or sensitive
   source documents, names, raw OCR text or evaluation manifests containing
   private content into the public repository.
2. Transcribe representative page text independently from the original image,
   **without copying the model output**. Label table rows/cells and sentence-page
   citations by checking the PDF manually. Include correct-abstention cases.
3. Copy the JSON example below to a **local file outside this repository** and
   adjust file paths. Paths resolve relative to the manifest. No web download,
   source-site crawling, upload or authentication occurs in the evaluator.
4. Run `uv run python scripts/pdf-evaluate.py --manifest /private/gold.json
   --output /private/pdf-eval-results.json`. The output explicitly labels the
   dataset as `synthetic` or `manually_labeled_real`.
5. Review each page's warnings and mismatched examples before interpreting
   aggregate metrics. Optionally supply explicit quality gates, such as
   `--max-character-error-rate 0.1 --min-citation-precision 0.99
   --max-wrong-citations 0`; these are **illustrative choices**, not
   empirically justified defaults. The CLI returns exit status 1 on a missed
   gate and records observed values. It refuses a threshold for a metric
   whose ground truth is missing. Do not merge until the representative
   newsroom sample and chosen targets have been reviewed.

### Manifest example

```json
{
  "dataset_name": "editorially-reviewed-sample-v1",
  "dataset_type": "manually_labeled_real",
  "documents": [
    {
      "id": "ministry-report-01",
      "pdf_path": "ministry-report-01.pdf",
      "source_url": "https://publisher.example/reports/ministry-report-01.pdf",
      "ocr_enabled": true,
      "ocr_language": "eng+hin",
      "pages": [
        {"page": 1, "expected_text": "Human-corrected page transcription"}
      ],
      "tables_fully_annotated": true,
      "tables": [
        {
          "page": 1,
          "candidate_index": 0,
          "expected_rows": [
            ["District", "Cases", "Reports"],
            ["Bhopal", "21", "17"]
          ]
        }
      ],
      "citations": [
        {"source_sentence": "An exact sentence from the original text.",
         "expected_page": 1},
        {"source_sentence": "Phrase absent from this document.",
         "expected_page": null}
      ]
    }
  ]
}
```

Include positive citations, ambiguous duplicates that must abstain,
numeric-heavy tables with repeated and merged cells, Hindi OCR scans,
mixed Hindi/English text, headings, footnotes, dates, 90-degree rotation,
and a document with no tables. Report each category separately. More than
one publisher and scan quality is necessary for a meaningful accuracy claim.

## Metric definitions (not estimates)

- **Character error rate (CER)**: Unicode NFC codepoint Levenshtein edits
  divided by reference codepoints; not grapheme-cluster error rate.
- **Word error rate (WER)**: whitespace-token edit count divided by reference
  tokens. Higher is worse; rates may exceed 100% with heavy insertions.
- **Table-cell precision and recall**: positional exact matches of labeled
  rows/columns against review-only table candidates. A candidate that is
  absent receives zero recall; guessed numbers do not count as matches.
  Rows must first be adjudicated in source order. Set
  `tables_fully_annotated: true` only after an editor has reviewed every
  page for tables, including pages with no tables. Extra candidates on
  *any page*, even one that already has a labeled table, are then counted
  as false detections. Without full labeling, extra candidates are reported
  as **unjudged**, never automatically called false positives. The optional
  `--max-false-table-candidates` gate refuses incomplete ground truth.
- **Citation precision**: correct page anchors divided by all proposed
  anchors. **Citation recall**: correct anchors divided by all expected
  anchors. Correct abstentions, wrong anchors, missed anchors and overall
  abstention rate are reported separately; avoid rewarding excessive silence.
- **Limitations**: CER/WER are not factual accuracy metrics; exact table cells
  do not establish statistical truth; page anchors do not independently verify
  the story. Labels, exclusions, sampling and acceptance thresholds require
  a human editorial decision. Never describe synthetic CI fixtures as a
  real-world benchmark.

## Safety and quality controls already implemented

- Source freshness/admission, robots policy, SSRF guards and byte cap are
  inherited from the crawler. PDF extraction does not perform independent
  network access.
- Raw artifact bytes are independently SHA-256 checked before storage.
  Local hard links and conditional S3 `If-None-Match` prevent duplicate-key
  overwrites, and a collided S3 object is byte-checked rather than trusted.
  Unsupported S3 conditional writes fail closed.
- Poppler and Tesseract subprocess timeouts; cumulative PDF-processing
  deadline; per-page output budget; page count and OCR attempt budgets;
  document text-character budget; raw snapshot immutability.
- OCR defaults **off**. When enabled in the Docker image, bilingual
  `eng+hin` is the default. OCR text remains explicitly unverified.
- Native PDF page hashes, offsets and originating PDF URLs are preserved;
  matches across pages, duplicate passages and mismatched source URLs abstain.
- Table previews are explicitly unverified, review-required and not promoted
  into automatic verification.

## Remaining external gates

- Evaluate a consented or openly licensed *real* reference corpus with the
  local harness. The synthetic one-page Hindi and table fixtures only prove
  that the code path works; they do not establish reliability on news sources.
- Linux PDF subprocesses now fail closed if `prlimit` is unavailable, and
  enforce per-process address-space (1 GiB), CPU (60 seconds), output-file
  (16 MiB) and core-dump (zero) kernel limits in addition to wall-clock
  timeouts. Docker installs util-linux. Windows does not yet enforce equivalent
  kernel limits. These controls **do not** isolate processes from the network.
- Perform an independent adversarial-PDF review and run converters in
  a separate restricted sandbox/container (network disabled, CPU/RAM/disk,
  process count, OS seccomp and filesystem controls). Per-process rlimits
  reduce resource exhaustion but are not a complete sandbox. Validate
  patched Poppler/Tesseract packages.
- Test inaccessible/slow/multi-column PDFs, failed native extraction,
  malformed streams, low-resolution screenshots, large reports, rotated scans
  and permission-protected documents; review failure logging and retries.
- The article intelligence source tab now presents page links, extraction
  warnings, OCR review labels and review-only table candidates. Analyst claim
  cards include an originating PDF page link when a unique anchor exists.
  Check these in a real browser with reviewer access, including mobile
  layout, inaccessible source URLs and keyboard navigation, before release.
- Review both stacked PRs before merging. The merge/deployment decision is
  intentionally separate from this evaluation task.
