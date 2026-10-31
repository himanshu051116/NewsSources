# News Intelligence 1.7.0 — Accuracy & Source Fidelity

This release focuses on measured acquisition/extraction/event-linking correctness rather than
adding a new intelligence subsystem.

## Fixed

- HTML RSS/feed directory pages are expanded safely instead of being discarded as invalid XML.
- Cross-publisher same-event matching uses contextual numeric anchors, expanded geography/event
  vocabularies, containment and a gated strong-anchor conjunction while retaining the existing
  `0.62` candidate threshold.
- Event matcher policy is now `event-matching-structured-lexical-v3`.
- Stored article versions carry publisher-page extraction-fidelity diagnostics where available.
- News and Article Intelligence surface extraction fidelity as Strong/Moderate/Weak, explicitly
  not a factual-truth probability.
- The news-feed article summary projection helper missing from v1.6.1 is restored and tested.
- Release contract tests are synchronized to the actual release version.

## Added

- same-event / hard-negative regression fixture covering cross-publisher maritime, ISRO paraphrase,
  Hindi election, hijacking, legal/sports and unrelated-topic cases;
- extraction-fidelity unit tests;
- `newsintel-accuracy-audit` and `scripts/accuracy-audit.ps1` for live laptop-side publisher audits.

## Schema

No migration is required. The Alembic head remains `0022_browser_recompute`.
