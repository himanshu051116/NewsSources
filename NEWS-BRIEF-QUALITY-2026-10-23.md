# Daily and weekly brief quality upgrade

The `/briefs` page now selects for useful reporting before source/topic variety. Daily covers the last 24 hours; weekly covers the last seven days and balances earlier developments with recent reporting. Both retain the 360-word reading budget, source links and saved reading preferences.

## What changed

- **Better selection:** public-interest signals and usable source text influence prominence. Routine horoscope, shopping and opinion content stays in the longer stream by default; relevant topic/keyword customization can include it. This uses transparent heuristics rather than a publisher-reputation or truth score.
- **More informative excerpts:** choose a source sentence that adds detail to its headline, while preserving attribution, numbers and uncertainty. Skip navigation, related-story lists, image metadata, repeated headlines, rhetorical questions and generic reaction lines. Do not invent a replacement when captured text is insufficient.
- **Less repetition:** conservatively group closely matching reporting and retain the original publishers. Different reported numbers and denials remain separate. Closely related updates to one event receive one short-brief slot; other reports remain available in More headlines.
- **A distinct weekly edition:** freshness decays more gently, selection balances publication dates, and a busy capture period is sampled across publishers and days. Weekly is no longer simply a longer window sorted toward the latest headlines.
- **Clearer presentation:** publication dates appear beside publishers; opinion and analysis have labels. About this brief distinguishes the selected publishers and dates from total available coverage and reports when readable source text is unavailable.
- **Responsive processing:** narrow SQL rows are ranked and sampled before body text is loaded. Duplicate matching uses bounded candidate buckets. Text/topic features are reused for unchanged article versions, and editorial processing runs outside the web event loop. The selector removes stories that cannot fit the remaining word budget together, avoiding repeated re-ranking after the brief is nearly full.

## Verification

- Full regression suite: **491 passed**, including the dedicated PostgreSQL integration database. Result: `.run/audit/pytest-digest-quality.xml`.
- After the last source-cleanup refinements: **25 focused tests passed**, covering source excerpts, qualification/attribution, metadata noise, opinions, personal feeds, duplicate updates, reported-number differences, reading limits, weekly date sampling and snapshot/pagination behavior.
- Seven rendered pages and 14 inline script blocks passed JavaScript syntax checks. Focused import/undefined-name lint passed; the new quality module passed its full configured Ruff check.
- `qa/verify_digest_quality.py` exercises the running API without changing user data: daily/weekly editions, word limits, source filters, publication windows, readable summaries and stable full-stream pagination. Evidence: `.run/audit/digest-quality-live.json` and the separate daily/weekly snapshots.
- Browser checks cover both Daily and Weekly, visible dates, source details and reading-time labels. Saved previews: `.run/audit/digest-quality-daily.png` and `.run/audit/digest-quality-weekly.png`.

Final live API sample on 23 October 2026, approximately 16:15 IST:

| Edition | Stories | Words | Estimated reading | Selected publishers | Publication dates |
| --- | ---: | ---: | ---: | ---: | ---: |
| Daily | 8 | 354 | 107 seconds | 6 | 2 |
| Weekly | 9 | 358 | 108 seconds | 6 | 5 |

The daily rolling 24-hour window crosses two calendar dates. The weekly window remains seven days; five dates contributed stories to this short selection. The first daily request took 13.1 seconds and the first weekly request took 21.8 seconds in this local sample. Later requests reuse text/topic features; they still read a fresh database snapshot. These measurements include active ingestion workers and are not service-level guarantees.

The measured 600-report profiling sample reduced selection work from about **12.8 seconds to 0.14 seconds** after fixing repeated re-ranking. These are local profiling measurements, not an end-to-end latency guarantee. A first request still performs more work than a refresh because excerpt/topic features need to be computed.

## Scope and limits

This improves selection and presentation of captured reporting. It does not independently fact-check publisher claims, translate reporting, or establish complete coverage of all news. Excerpts can be visibly shortened with an ellipsis; the named original source remains available for full context. Publication dates determine eligibility, with a labelled capture-date fallback when a source date is missing.

The local PostgreSQL container, API and news workers are running. Docker's startup blocker was resolved by preserving stale socket-only runtime directories and letting Docker recreate them; database files and configuration were retained.
