# Daily and weekly news briefs

Open `/briefs` for the simple reader interface. Daily covers the previous 24 hours;
weekly covers the previous seven days. Headlines open the original publisher.
Open **Sources** for other coverage and the saved report. `/news` offers the full
current stream with 24-hour and 7-day choices, loaded-headline search and pagination.

The short edition balances topics and publishers within a 360-word budget
(estimated at 200 words/minute). **More headlines** continues the matching news
without repeating the short edition's stories. **About this brief** contains
the reporting counts, exact dates and coverage explanation. A two-minute
selection cannot include every headline.

Use **Personalize** to select topics, then **Show my brief** to read. **All topics**
clears the topic selection. Publishers, reporting languages and included or hidden
phrases are under **More options**; publisher and language lists use searchable
checkboxes. Empty selections mean all. Include phrases match any phrase;
exclusions remove any matching report. Automatic topics use publisher sections,
the headline and opening text. Keywords search
the headline and first 6,000 characters of captured text. Reports stay
in their original language. **Save these choices** lets you name a feed and keep
it on your account. Return to it under **My feeds**; existing saved streams remain
available and can be updated or deleted. The feed picker appears when a feed is
saved. **Clear filters** returns to all news.

Headlines open the original report in a new tab when its source URL is available.
The publisher is visible below each sentence; **Sources** expands publication
details, language, other publishers and links to the saved article.

## Coverage and grounding

- Editions use already captured reporting, not the entire internet. Ingestion
  delays and publisher availability affect coverage.
- Each line is a shortened source excerpt, preserving its attribution. No remote
  model or paid AI API is called. A missing body is labeled explicitly.
- Exact headlines or substantial identical content are grouped across sources.
  Different reports in the same event are retained unless their exact identity
  matches. This conservative rule may leave similar headlines in the longer stream.
- Common calculator, topic, author, search and undated category pages are excluded
  from editions. They remain in the underlying archive. The short edition requires
  a publication date and enough readable source text.
- The selected article version's publication time defines the current window.
  Capture time, page modification time and sitemap `lastmod` do not establish
  publication time. Undated captures can appear in **More headlines**, explicitly
  labelled **Publication date unconfirmed**, and never enter the current short brief.
- Archive reprints and clearly expired live sessions or daily services stay out
  of current views, including personalized briefs. Their labels remain visible in
  the longer stream. Expiry detection is conservative and heuristic; ordinary
  current reporting about historical events remains eligible.
- Longer-stream requests reuse the edition timestamp. The visible **As of** time
  identifies the snapshot. After five minutes an update prompt appears; returning
  to an idle brief refreshes it while preserving active editing and longer reading.
- At most 6,000 eligible reports are examined per request, taking a round from
  each publisher before its next report. High-volume editions explicitly state
  that both views are sampled. Narrowing filters can improve coverage.
- Multiple reports do not establish independent corroboration or factual truth.

## API and persistence

All endpoints require an approved account with `CONTENT_VIEW`. Existing cookie
CSRF protection applies to write and preview requests.

- `GET /api/v1/digests/options`
- `POST /api/v1/digests/preview` with `period`, `filters`, optional timezone-aware
  `as_of`, `full_stream`, `current_only`, `offset`, and `page_size`. `/news` requests
  `full_stream: true, current_only: true`; filtering occurs before pagination.
- `GET` / `PUT /api/v1/digests/preferences`
- `GET` / `POST /api/v1/digest-streams`
- `PUT` / `DELETE /api/v1/digest-streams/{stream_id}`

The preview returns reading time, actual coverage, source references and the next
offset. Saved streams are scoped to the authenticated user's existing JSON
metadata, capped at 20 per account. Mutations lock the account row and preserve
unrelated metadata. No migration or additional background worker is required.

Items include `freshness_status` (`current`, `date_unconfirmed`, `expired`, or
`historical`) and an optional `freshness_reason`. Editions count retained flagged
stories in `excluded_stale_or_uncertain`. These are editorial date signals, not
fact-checking certificates. See `READER-UI-FRESHNESS-AUDIT-2026-10-31.md` for the
latest checks and remaining limits.

Regression checks live in `backend/tests/unit/test_news_digests.py` and the
digest cases in `backend/tests/integration/test_article_repository_postgres.py`.
`qa/verify_rendered_js.py` includes the actual `/briefs` HTML scripts.

## Local verification — 23 October 2026

- Full regression suite: 455 passed, including PostgreSQL tests against the
  separate audit database. After the final topic refinement, all 19 focused
  digest and persistence checks passed again.
- New feature modules pass Ruff and strict mypy checks. Six rendered pages,
  including `/briefs`, passed JavaScript syntax checks (12 inline script blocks).
- Live daily and weekly API checks returned 106- and 105-second editions from
  three and six reporting publishers respectively; eight publishers were
  configured. Counts change as ingestion continues.
- Live stream create/reload/update/delete checks preserved existing streams;
  an unknown stream ID returned 404. Browser checks verified period switching,
  custom filters, saving a sports stream and expanding to 50 longer-stream stories.
- The local API and seven ingestion/analysis workers were running after deployment.

Machine-readable evidence is in `.run/audit/pytest-digests.xml` and
`.run/audit/digests-live.json`. These checks establish feature behavior; topic
classification remains heuristic and source excerpts remain dependent on capture quality.

The simplified reading interface was checked separately: 15 targeted tests
passed, Ruff passed, and the six-page JavaScript check passed again. Live mobile
checks covered topic/language checkboxes, applying choices, source details and
saving a feed. Expanding an English sports brief displayed 20 headlines with
no repeated headlines from the short edition. The disposable UI test feed was removed.
