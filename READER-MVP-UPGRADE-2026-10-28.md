# Reader MVP upgrade — 28 October 2026

The daily/weekly reader now remembers account-owned reading choices, rejects more misleading source text, avoids a known bilingual duplicate announcement, and prepares excerpts when article versions are captured. Recent rediscovered reports can also be fetched again to capture corrections.

## Delivered behavior

- **Return to your choices:** period, topics, languages, publishers, phrases and chosen saved feed persist in account metadata. Choices restore before the first edition request, avoiding an all-news flash and a second expensive request. Rapid changes save in order. Reset clears choices; deleting a selected feed clears its default reference. Account ownership checks and row locks preserve unrelated metadata.
- **Cleaner sentences:** reject repeated caption fragments, incomplete caption text and historical context without a corresponding headline date. Existing attribution, uncertainty and truncation guards remain. Reports without usable text stay available in the expanded stream with original sources.
- **Better topic handling:** explicit criminal proceedings and police investigations of deaths go to law/justice before incidental hospital or finance references can influence their category. Generic “final” and rupee-crore mentions no longer receive an automatic public-interest boost.
- **One slot for a known bilingual duplicate:** matching Indian central-government dearness-allowance approvals share a short-edition slot when the percentage matches and publication times are within 36 hours. Negative/proposed statements and different percentages remain separate. Full reports retain their original language and sources. This is a limited tested rule, not universal multilingual event matching.
- **Prepared version excerpts:** derived metadata includes a policy identifier and publication year. The API reuses valid preparation and falls back to current analysis when absent/stale. A changed article version gets its own preparation. Original article text is preserved.
- **Bounded correction refresh:** a successfully processed article rediscovered at the same URL becomes eligible for another fetch after 24 hours if its actual stored publication date is within seven days. Repeated discovery cannot duplicate queued/leased work. Rejected URLs and old archive material are not revived, even if a feed reports a newer modification date. Corrections can create new versions while preserving the earlier reporting.
- **Home entry:** a prominent “Read my brief” panel appears above operational metrics.

## Preparation and validation

Prepared **8,425 existing recent versions** with `python -m newsintel.maintenance.prepare_digest_excerpts --days 8 --limit 20000`. The bounded process updates only derived `digest_excerpt` metadata with an atomic JSON merge. New captures prepare themselves. No schema migration was required. API, poller and article worker were reloaded; the other workers remained running.

**520 tests passed** in 49.58 seconds, with 895 warnings. Four new dedicated PostgreSQL regressions cover correction capture into two versions, guarded rechecks, preference ownership/deletion and preparation preserving unrelated metadata. Evidence: `.run/audit/pytest-reader-upgrade-20261028.xml`.

Seven pages / fourteen inline scripts passed JavaScript syntax checks. Focused import/name lint passed. The actual initialization/Refresh handlers were checked with failing requests, restored choices, retained selection and ordered preference writes using `qa/verify_digest_recovery.py`.

First live requests after API restart:

| Edition | Request time | Eligible / checked | Stories | Words | Selected publishers | Publication dates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Daily | 2.628 s | 1,486 / 1,486 | 9 | 357 | 6 | 1 |
| Weekly | 9.372 s | 7,802 / 6,000 | 8 | 356 | 5 | 7 |

The earlier weekly sample took 25.589 seconds. These are point-in-time measurements during ingestion with different source counts, not a controlled benchmark or latency guarantee. Both editions stayed within the 360-word / 120-second reading estimate and excluded unreadable summaries, archive/opinion/service items by default. Evidence: `.run/audit/reader-upgrade-live-20261028.json`; runner: `qa/verify_reader_upgrade.py`.

Browser verification confirmed the upgraded daily display, selecting Weekly, saving that account preference, and restoring Weekly after a full page reload. Preview: `.run/audit/reader-upgrade-20261028.png`. The live account preference/readiness check is recorded in `.run/audit/reader-upgrade-preferences-20261028.json`.

## Remaining limits

Weekly generation remains slower than the proposed three-second target. Topic/phrase filters still run after the bounded 6,000-report sample. Broader cross-language grouping, editorial importance and extraction quality need human-reviewed evaluation. Correction capture requires rediscovery, eligibility and worker capacity; it is not immediate. Older/undated articles do not receive this automatic recheck.

The local Docker startup problem and unattended operation remain separate work. Public-launch readiness, exhaustive coverage and independent factual verification are not established by this upgrade.
