# News Intelligence 1.8.0 — Accuracy Measurement & Adjudication

This release focuses on measuring where the system is correct, where it abstains, and where errors enter the pipeline. It does not introduce a universal "news accuracy" score.

## Key changes

- Verification benchmark methodology v3 with decision coverage, abstention rate, decided-case accuracy/F1 and unsafe high-confidence error rate.
- Quality-gate support for minimum decision coverage, minimum decided accuracy and maximum unsafe high-confidence error rate.
- Confidence calibration excludes `not_checkable` abstentions; abstention behaviour is measured through coverage instead.
- Human-adjudication JSONL export/import workflow for building held-out benchmark sets from the local article corpus.
- New `/accuracy` analyst workspace for benchmark, corpus-audit and quality-gate results.
- 20-case same-event/hard-negative event-link regression set spanning multiple domains and Hindi/English examples.
- Event matcher methodology advanced to `event-matching-structured-lexical-v4`; short-location substring false positives and generic-anchor over-merging are corrected.
- Live publisher extraction audit supports aggregate fidelity summaries across multiple URLs.
- Older benchmark rows remain backward compatible: decision metrics that did not exist at creation time are shown as unmeasured, not zero.
- No database migration is required; the schema head remains `0022_browser_recompute`.

## Accuracy interpretation

Version 1.8 reports three distinct concepts:

1. publisher-page extraction fidelity;
2. event-link precision/recall on an adjudicated pair set;
3. claim-verification accuracy/coverage on an adjudicated claim set.

These dimensions should not be averaged into a single truth score.
