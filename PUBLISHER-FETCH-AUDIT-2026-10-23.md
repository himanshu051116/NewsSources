# Publisher fetching audit — 23 October 2026

Publisher acquisition had multiple independent faults. The fixes below are running locally at `http://127.0.0.1:8010`. Verification followed the browser request through the API, discovery records, article workers, stored article versions and source counters.

## Confirmed faults and fixes

| Fault observed in the local installation | Fix |
| --- | --- |
| HTTP 304 responses were treated as redirects without a Location header. The initial sample contained 1,729 such Times of India failures. | Only 301, 302, 303, 307 and 308 enter redirect handling; 304 completes as unchanged content. Redirect destination validation remains enabled. |
| Thousands of old child sitemaps displaced live feeds. Some manual jobs scheduled over 9,000 channels for one publisher. | Prefer live feeds and news sitemaps, share polling slots across publishers, limit manual checks to 20 current channels per publisher, and scan index children in bounded rotating batches. Explicitly dated archive maps outside the recent window are excluded from new index discovery and manual selection. |
| Concurrent discoveries raced on the unique URL fingerprint and channel endpoint. | Atomic inserts with conflict handling reuse the winning candidate/channel instead of failing an otherwise healthy feed. |
| Article discovery budgets existed in configuration but were not enforced for manual jobs. | Enforce the configured limits transactionally: by default 300 new URLs per publisher and 2,000 per job. Reaching a budget stops admission cleanly. Previously known URLs remain deduplicated observations. |
| Disabled BBC work occupied 22,301 ready/retry/leased entries, including obsolete leases. | Disabled publishers are excluded from discovery and article leasing, and unfinished candidates are paused with lease fencing. Disabling a publisher cancels its dedicated pending fetch jobs. |
| One publisher's ongoing fetch caused Fetch all to fail for every publisher. | Reuse an existing publisher job; Fetch all schedules idle publishers while leaving ongoing work attached to its existing job. Repeated requests do not duplicate work. |
| Completing an automatic poll could erase a manual request scheduled during that poll. | Match completion to the run's original job ID. Preserve newer manual job tags and keep those channels due immediately. |
| One unusually long headline could invalidate an entire feed or homepage poll. | Bound publisher-provided title, external ID and raw date metadata before constructing admission commands. Public request validation is unchanged. |
| A robots-policy refusal inherited from OSError and was reported as database unavailability. | Record the blocked channel, respect the policy and continue the other channels. |
| Expired article leases could remain behind a continual stream of newer stories. | Recover expired leases before fresh candidates within each publisher, while retaining fairness between publishers. |
| Source timestamps advanced when a fetch was merely scheduled; rejected non-news URLs inflated failure counters; jobs could report success after every poll failed. | Show actual successful-check times and latest saved-article times; distinguish failed articles from excluded URLs; persist derived job state and retain a processing-articles phase until observed pending articles finish. |

## Existing local data repair

Applied once with `qa/repair_publisher_fetch.py --apply` while the affected workers were stopped:

- Paused 16,313 explicitly dated archive channels: Al Jazeera 9,667; TOI 3,371; Aaj Tak 3,195; ABP 80.
- Paused 22,301 unfinished candidates belonging to disabled publishers.
- Cancelled 26 oversized or orphaned legacy jobs and cleared their scheduling links.
- Scheduled current feed, homepage and news-sitemap checks.
- Preserved stored articles and discovery rows. BBC and Dainik Bhaskar remain disabled.

Original affected records were backed up before the transaction in `.run/backups/publisher-fetch-repair-20261022T235344.json`. The repair utility defaults to a dry run. This is a record-level backup; the earlier full local PostgreSQL backup also remains available.

## Verification

- **480 tests passed**, including PostgreSQL integration tests against the separately migrated `newsintel_audit_20261021` database. No live database reset was used. Machine-readable result: `.run/audit/pytest-publisher-fetch.xml`.
- Regression cases cover 304 handling and redirect validation, publisher fairness, archive dates and index cursor rotation, concurrent insert conflicts, manual article limits, disabled work, all-failed jobs, repeated fetch requests, the poll/manual scheduling race, oversized headlines, robots refusals and expired-lease recovery.
- Focused Ruff import/undefined-name checks passed on the changed acquisition files and tests.
- The rendered JavaScript check passed for seven pages and 14 inline scripts, including Sources.
- After restarting the API/poller and article worker, browser Fetch all returned **202 Accepted**. Repeating a publisher fetch while it was running also returned **202**, without the former conflict error. Job-status requests returned 200 and counters advanced.

The final recorded sample is **2026-10-23 00:14:36 UTC / 05:44:36 IST**. Since the repair/restart sequence began at 23:54:18 UTC, 115 new articles were saved across all six active publishers:

| Publisher | New stored articles in this sample |
| --- | ---: |
| Aaj Tak | 3 |
| ABP | 23 |
| Al Jazeera | 11 |
| Indian Express | 29 |
| The Hindu | 21 |
| Times of India | 28 |

Saved article versions contain extracted text and source URLs. Fresh successful checks were observed for all six publishers. The post-restart poll records include valid 304 completions; no new missing-Location or oversized-title errors occurred in this verification window.

The browser job `01a16615-240c-7bfb-b8de-3c0dc7afe300` finished its discovery channels and entered `processing_articles`: **0 channels remaining, 31 articles saved during the job, 115 newly queued candidates and 2,194 observed articles still waiting**. Its observed waiting count includes candidates that already existed before this job. The whole active article queue held 3,201 candidates; **stale article leases and stale polling leases were both zero**. The full crawl is still processing asynchronously, so this audit does not claim that the backlog has completed.

## Remaining operational limits

The Hindu's video-sitemap endpoint explicitly refuses this crawler in robots policy. That channel is recorded as blocked; other allowed Hindu sources and article captures succeeded. Individual publisher/network/extraction failures can still occur and are retained in source health. Historical cumulative failure counts are retained rather than cleared to make the dashboard appear healthy.

Daily and weekly summaries cover articles actually captured by the platform. This work verifies acquisition from the configured active publishers; it does not establish complete coverage of every publisher or every story on the web.

Evidence: `.run/audit/publisher-fetch-before.json`, `.run/audit/publisher-fetch-after.json`, `.run/audit/publisher-fetch-live-proof.json`, and `.run/audit/publisher-fetch-fixed.png`. The final proof file is the authoritative sample for the counts above; background processing continues after it was written.
