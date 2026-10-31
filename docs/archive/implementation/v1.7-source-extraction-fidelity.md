# Accuracy & Source Fidelity 1.7.0

**Release:** 1.7.0  
**Alembic head:** `0022_browser_recompute` (no schema migration required)

Version 1.7.0 is a correctness-focused release. It does not claim that article or claim
content is factually true. It improves whether publisher sources are discovered, whether
publisher HTML is faithfully extracted, and whether reports about the same real-world event
are linked consistently.

## Source discovery

- HTML pages reached through RSS/feed hints are now inspected as syndication directories.
- Feed-directory expansion is bounded to one hop and a capped candidate count.
- Cross-origin feeds such as FeedBurner are accepted only when feed-specific evidence is strong.
- Existing SSRF/public-network and endpoint validation controls remain in force.

## Event identity

- Event matching advances to `event-matching-structured-lexical-v3`.
- Contextual numeric facts such as `24 crew` and `240 nautical miles` are treated as stronger
  event anchors than bare numbers.
- Maritime incident vocabulary, geography and Unicode/Hindi event vocabulary are expanded.
- Containment similarity improves short-wire-vs-long-report comparisons.
- A gated conjunction bonus applies only when time, event type and strong structured anchors
  agree; the global candidate threshold remains unchanged.
- A positive/hard-negative pair fixture guards against known false merges and missed matches.

## Extraction fidelity

Each article version can carry an extraction-fidelity report that checks extracted fields
against independent publisher-page signals still present in the fetched HTML:

- headline metadata consistency;
- canonical URL consistency;
- publication-time consistency;
- structured article-body coverage when available;
- structured numeric-fact retention.

The scope is explicitly `publisher_page_extraction_fidelity_not_factual_truth`.

## Live accuracy audit

Run on a machine with outbound network access:

```powershell
.\scripts\accuracy-audit.ps1 -Url "https://publisher.example/story"
```

or:

```powershell
.\.venv\Scripts\python.exe -m newsintel.accuracy_audit --url "https://publisher.example/story" --json
```

This performs a real safe fetch, extraction and fidelity assessment. It is intended to detect
fetch/extraction defects, not to adjudicate whether the publisher's reporting is true.

## No migration

The schema head remains `0022_browser_recompute`. Fidelity metadata is stored inside the
existing immutable article-version metadata document.
