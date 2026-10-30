# Critical functionality and MVP review — 27 October 2026

Follow-up: [28 October reader upgrade](READER-MVP-UPGRADE-2026-10-28.md) addresses remembered choices, prepared excerpts, specific quality defects and bounded correction refresh. The findings below record the reviewed state; the follow-up documents what changed and what remains open.

Review completed on 28 October 2026. The measured edition samples and regression runs below were recorded on 27 October; they are labelled by their actual capture date.

## Verdict

The application has a working news-reader prototype and substantial analyst tooling. It is suitable for an invited, supervised pilot. It is **not yet a dependable public MVP for everyday news readers**, and the evidence does not support calling it fully developed or production-proven.

The reader promise should be: **“Key developments from your selected publishers in about two minutes, with original sources and visible coverage.”** A short selection cannot be complete coverage of every publisher or every important event.

This review follows the reader journey from UI to API, database and response. It includes code review, regression tests, real captured editions, publisher operations and the running browser. Passing tests demonstrate specific behavior, not editorial judgment or sustained availability.

## Functionality assessed

| Capability | Assessment | Evidence / practical limit |
| --- | --- | --- |
| Daily and weekly briefs | Implemented and responding | Rolling 24-hour / seven-day windows; word budget; source links; full-stream pagination. Weekly is selected reporting across a period, not an authored account of how each story evolved. |
| Publisher ingestion | Working after local recovery; operationally fragile | Six active publishers returned successful checks and new articles. Fetching is asynchronous and a substantial queue remains; a successful schedule is not completed coverage. |
| Excerpts and deduplication | Improved, still heuristic | Concrete merging, qualification and navigation-text bugs repaired. No independent truth verification or measured editorial-quality guarantee. |
| Personalized feeds | Mechanically functional, quality needs work | Topics, publishers, languages and phrases apply; saved feeds are scoped to accounts. Misclassified articles can still enter a topical feed. |
| Saved reading context | Partial | Saved feeds persist, but reopening the page starts at daily/all-news rather than restoring a chosen default feed. |
| Freshness / coverage | Clearer after fixes | Generation time and capture time are distinct. Capture time is the newest **first capture among checked reports**, not a last-poll timestamp or proof that every source is up to date. |
| Reader experience | Mixed | The brief page is simple; home/navigation still emphasize events, investigations, conflicts and quality operations. |
| Public access / deployment | Unproven | Private approved-user access suits a pilot. Production login, restart/soak behavior, recovery and real-reader acceptance still need their own validation. |

## Confirmed bugs repaired during this review

| Severity | Before | Repair |
| --- | --- | --- |
| High | Identical headlines could merge reports with different casualty counts or denials. | Check conflicting details even on exact headline matches; preserve separate reports. |
| High | A newer opinion article could absorb matching news and remove the entire group from the default brief. | Keep report types separate in grouping. |
| High | A 30-word excerpt could cut off a later “has not been approved” or attribution. | Reject unsafe sentence cuts and use another source sentence or an unavailable-summary label. This is a conservative guard, not a universal semantic guarantee. |
| High | Headline clipping could remove a meaningful final clause. | Preserve the complete normalized original headline; count it in the overall reading budget. |
| High | “Updated” showed request-generation time even when captures were old. | Show “Brief generated,” actual capture information, and a warning when the newest checked capture is at least six hours old. |
| Medium | A manual publisher began automatic polling after its first explicit check. | Completion clears the recurring schedule, while preserving a newer explicitly requested fetch. Regression coverage includes success, not-modified and failure outcomes. |
| Medium | Strong historical success could keep a badly overdue automatic channel “healthy.” | Cap overdue channel health at watch/degraded; manual sources do not have an assumed automatic cadence. |
| Medium | Student-led national election stories and university medical research could be categorized as education. | Narrow subject-sensitive corrections, preserving genuine campus/exam stories. Other classification errors remain. |
| Medium | Explicit archive reprints appeared in the default current-news brief. | Label archive reporting and keep it in the expanded stream or relevant personalized feeds. |
| Medium | Joined Hindi navigation text appeared at the start of excerpts. | Remove the anchored “और पढ़ें” navigation prefix before sentence selection. |
| Medium | A temporary setup request failure left personalization disabled; the brief's Refresh button did not retry loading preferences. | Refresh now retries failed setup requests, retains the chosen saved feed, and resumes ordinary edition-only refresh after recovery. |
| Medium | Starting all workers before API readiness could exhaust the local startup window. | Wait for API readiness before starting competing workers; retain the final readiness check. |

## Remaining issues, in priority order

1. **High — Publisher corrections are not reliably refreshed.** A successfully processed candidate remains fetched when the same URL is rediscovered. Metadata can update without fetching a new article version. Version-history support therefore does not establish an end-to-end correction-refresh workflow. Add a bounded recrawl policy using source modification signals and conditional requests; verify a changed story at the same URL reaches the brief. Relevant code: `application/acquisition/service.py` and `infrastructure/db/acquisition_repositories.py`.

2. **High — Editorial usefulness is not established.** Real editions included a 1976 archive reprint as current business reporting, weak introductory sentences, and topic errors. A browser-tested Science & health selection included crime reports, demonstrating that the controls can work while classification is wrong. The explicit archive/navigation cases were fixed in this audit; broader ranking and classification need a reviewed multilingual evaluation set. Public-impact keywords and topic variety are not sufficient evidence that the most important stories were selected.

   The final 28 October browser sample further confirmed this limit: a video/shorts capture led the brief with an internal-looking token and repeated caption text; the same dearness-allowance announcement occupied separate Hindi and English slots; and a selected context sentence referred to a historical incident instead of explaining the current development. These remain open quality defects. The current conservative lexical grouping does not provide reliable cross-language event deduplication. The screenshot deliberately retains these observed problems: `.run/audit/mvp-brief-20261028.png`.

3. **High — Continuous availability and timely capture are unproven.** At the beginning of the check, Docker, API and all workers were stopped. Docker had a repeatable stale runtime-socket startup failure. Existing data was preserved and services restored, but a local repair does not solve unattended hosting/restart reliability. Later interruptions also left the local stack stopped, including the 28 October continuation. The shutdown cause was not established. The final browser check also captured database connection timeouts returning 500 for personalization options and saved feeds during startup load; both reads then recovered. UI Refresh now retries failed setup, while the database-capacity/startup cause remains an operational issue. The app needs a supervised operating environment, recovery checks, and a sustained source trial before public reliance.

4. **High — Cold weekly generation is too slow for the main reading journey.** The initial live weekly request took **36.912 seconds** for 4,117 matching stories. The final HTTP sample after optimization took **25.589 seconds** for 4,298 matching stories; subsequent full-stream pages took **3.306 and 4.669 seconds**. These are point-in-time measurements during ingestion, not a controlled benchmark. Optimization replaced repeated per-term topic scans with one scan and reduced text-cleanup overhead. Instrumented weekly profiling fell from **54.3 to 36.2 seconds** with 4,291 versus 4,336 reports; profiler timings are distinct from HTTP latencies. Source-sentence selection remains the largest CPU cost. Establish and measure a first-load budget rather than relying on a warm development process.

5. **Medium — Topic/keyword filters can miss reports outside the sample.** Publisher and language filters precede the 6,000-report cap; topic and phrase filters run afterward. A rare interest can return nothing despite matching reports outside that sample. UI guidance now states this accurately. Filter-aware retrieval/indexing remains needed at larger volumes.

6. **Medium — Returning readers do not resume their preferred brief.** Feed persistence works, but selected feed/period is not restored. Add a per-user default or last-used preference with explicit reset behavior.

7. **Medium — The product entry point targets analysts.** `/app` foregrounds events, conflicts and attention metrics. For the stated audience, make the brief the primary landing journey and keep investigation tools secondary. This is a product change, not an authentication bypass.

8. **Medium — No demonstrated launch acceptance or user value.** Existing runbook gates require a 24-hour load run, 72-hour restart soak, seven-day source trial, database restore drill, production access tests and human review. This audit does not substitute for them. No real-reader retention or usefulness study was performed here.

## What a credible reader MVP needs next

| Order | Deliverable | Proposed acceptance evidence |
| --- | --- | --- |
| 1 | Current, dependable source capture and correction refresh | Seven-day six-publisher trial; source-specific freshness and failures visible; changed-URL-content scenario passes. |
| 2 | Reviewed editorial quality | Review at least 100 English/Hindi items over daily and weekly editions; measure topic correctness, misleading truncation, duplicate developments and missing important events. Treat zero material meaning reversals as a release requirement. |
| 3 | Fast brief delivery | Measure cold and warm p50/p95 with concurrent readers on the intended host. A proposed target is p95 under three seconds for the primary brief, with any generation delay shown honestly. This is a target, not an achieved result. |
| 4 | Brief-first return journey | Readers open their chosen daily/weekly feed directly; can change it and return without losing preferences. |
| 5 | Small invited usability trial | Observe readers find a useful brief, understand its coverage, change interests and open original sources without assistance. Record feedback and repeat use before expanding features. |

Advanced knowledge graphs, verification dashboards and investigation workspaces may remain available, but adding more of them will not resolve the reader MVP's core quality and reliability gaps.

## Verification record

- Baseline without database integration configured: **476 passed, 16 skipped**. The skips were not reported as successes.
- After the main fixes, with the dedicated rollback-only PostgreSQL audit database: **508 passed**, 859 warnings, 49.63 seconds. Evidence: `.run/audit/pytest-mvp-20261027.xml`.
- After archive, navigation and topic-performance fixes: **511 passed**, 859 warnings, 49.55 seconds. Evidence: `.run/audit/pytest-mvp-20261027-final.xml`. After the final headline-preservation change, all **29 digest unit tests passed** again. The full suite was not rerun after that final isolated change.
- Rendered JavaScript: seven pages / fourteen inline scripts passed after the final UI changes. Focused F/I lint passed across changed implementation files and the new runtime audit.
- Initial live evidence: `.run/audit/mvp-runtime-20261027-before.json`. Twelve core GET endpoints returned 200; daily/weekly previews and pagination returned 200; invalid `monthly` input returned 422.
- Initial live daily: four stories / 174 words / four selected publishers immediately after services resumed. Weekly: nine stories / 353 words / five selected publishers. Counts are point-in-time samples, not coverage guarantees.
- Final 27 October HTTP sample: daily **nine stories / 342 words / six publishers / 1.573 seconds**; weekly **eight stories / 352 words / six publishers / six publication dates / 25.589 seconds**. Both fit the 360-word, two-minute estimate and excluded unreadable summaries, opinion, service and archive items from the default short edition. Evidence: `.run/audit/mvp-runtime-20261027.json`.
- Browser verification covered daily/weekly switching, visible generation/capture dates and topic customization. The final weekly display showed six publishers and eight stories. This confirms UI behavior while leaving editorial relevance as an open acceptance issue.
- Live publisher fetch: `.run/audit/mvp-fetch-job.json`. The job was scheduled and was processing during the review. Its counters and the stored article total increased; it was not claimed completed.
- Performance profiling: `.run/audit/profile-digest-mvp-after-20261027.txt`; equivalent keyword-boundary, nested-phrase and score behavior is regression-tested.
- Local schema: `0033_grounded_news_explainer`; stored data retained. Docker recovery preserved only verified zero-byte socket runtime folders; no database reset was performed.
- 28 October deployment check: API liveness, database readiness and status returned 200 after local recovery; 16,599 stored articles were present at that snapshot. Evidence: `.run/audit/mvp-deployment-20261028.json`. The final API reload activated setup recovery while the seven workers remained running.
- Setup-recovery regression exercises the actual JavaScript initialization and Refresh handlers with failing options/feed requests, successful retry, preserved feed selection and subsequent ordinary refresh. Evidence: `.run/audit/digest-recovery-check-20261028.json`; runner: `qa/verify_digest_recovery.py`. Seven rendered pages / fourteen script blocks passed again after this last UI fix.
- Final 28 October browser check: daily brief rendered nine stories, six publishers, current generation/capture labels and an enabled Personalize control. Options, saved feeds and preview requests returned 200 after the API reload. Preview evidence: `.run/audit/mvp-brief-20261028.png`. This verifies recovery and rendering while preserving the remaining content-quality findings above.

The app is a modular FastAPI/PostgreSQL system. These checks cover the everyday-reader MVP. Independent factual verification and the accuracy of advanced research features require separate evaluation.
