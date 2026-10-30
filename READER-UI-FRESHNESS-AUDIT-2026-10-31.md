# Reader UI and news freshness audit — 31 October 2026

The local reader has been simplified and its current-news selection tightened.
Daily means the previous 24 hours; Weekly means the previous seven days. Every
edition displays its snapshot time. Work began on 30 October and continued past
midnight in Asia/Calcutta; machine evidence retains the starting date in its filenames.

## Reader experience

- `/briefs` and `/news` use a compact reader navigation bar. Research and publisher
  administration remain accessible under More with the existing access rules.
- Daily, Weekly and Personalize are the main brief controls. Publisher/language
  choices and saved feeds remain optional. Selected topics survive reloads.
- Headlines link to the original publisher. Dates include year and time; source
  details and the saved report are available without crowding the headline.
- Phone navigation, touch controls, wrapping headlines and both appearance modes
  were checked. A theme inheritance bug that mixed light backgrounds and dark cards
  was corrected. The tested phone layout had equal content and viewport widths.
- An edition older than five minutes prompts for an update. Returning to an idle
  brief refreshes it; editing and longer-stream reading are preserved. Restoring a
  saved feed also restores its editable name.
- Latest news uses publication-filtered results, a clear 24-hour/7-day selector,
  a search over loaded headlines and stable pagination. Older material remains in
  the archive.

## Confirmed problems and fixes

| Finding | Resulting behavior |
|---|---|
| Capture time or a legacy article-row date could make an undated item appear current | Current briefs require the selected stored version's publication date. Capture time is explicitly labelled in the longer stream. |
| Atom `updated`, JSON Feed `date_modified` and sitemap `lastmod` could be treated as publication | These fields no longer supply publication dates. Genuine publication fields remain separate. |
| The longest structured Article/hydration object could belong to a related story | Extraction matches canonical/fetched URL and page headline, preserves meaningful query parameters, rejects other-story URLs and abstains on ambiguous candidates. Page headlines take precedence over longer embedded entries sharing the canonical page. |
| Generic page dates, invalid first dates or metadata in related containers could supply a wrong date | Only publication-specific fields are used; parsing continues past invalid values. Modification time stays separate. |
| Undated captures, archive reprints and ended live/daily pages could enter short personalized briefs | Explicit freshness statuses apply before short selection and before current-stream pagination. Personalization does not bypass this gate. |
| Dated school-assembly roundups and utility advice could occupy weekly news slots | Dated roundups expire against the snapshot; roundups and utility guides are service content and stay out of the default short edition. |
| A background sentence about a different named person, or a near-repeat of a headline, could become the explanation | Leading name anchors, including initials, and added-information checks reject these excerpts. Prepared excerpt metadata uses policy `digest-excerpt-v5`. |
| Robots denial inherited `OSError` and caused a worker-wide database backoff | It becomes a terminal access-blocked article result; unrelated publisher work continues. Robots restrictions remain respected. |

The short brief excludes `date_unconfirmed`, `expired` and `historical` items.
The longer stream retains them with reasons. Ordinary current reporting about
historical events remains eligible. Expiry uses clear archive/time-sensitive signals,
dated headings and the edition snapshot; it is not a universal event-expiry detector.

## Verification

Reader story: open Daily/Weekly or Latest news → authenticated preview API →
PostgreSQL version selected as of the edition timestamp → source-attributed,
dated response → rendered reader page.

- **546 tests passed**, including the dedicated PostgreSQL regression database.
  New cases cover old/future/undated publication, legacy article-row fallback,
  expiry under personalization, snapshot stability, structured-article identity,
  related metadata, excerpt subject changes and robots denial handling.
- Seven rendered pages, 14 script blocks, no JavaScript syntax errors. Modified
  modules pass Ruff's syntax, undefined-name and import checks.
- The shipped brief script passed controlled-clock checks for stale prompts,
  return refresh, preservation of editing/reading, restored feed names and date labels.
- Live daily/weekly checks enforce the 360-word/two-minute budget, publication
  windows and current status. Database checks match each selected headline and
  timestamp to the selected article version. Current-stream pagination is checked
  for duplicate-free continuation at the same snapshot time.
- Archived HTML is hash-checked and re-extracted for the selected daily/weekly
  sample. All **17** sampled selections matched publisher headlines and publication dates.
- The recorded live check selected **8 daily stories in 2.756 seconds** and
  **9 weekly stories in 8.345 seconds**, both within the reading budget. It kept
  5 flagged daily matches and 234 flagged weekly matches out of the short brief.
  These counts change as ingestion continues.
- Browser checks covered personalization and reload, mobile wrapping, light/dark
  colors, a 50-story longer-stream expansion, loaded-headline search and news pagination.
  Latest news expanded from 50 to **100 distinct saved reports**. The final brief
  restored Weekly, no filters and the original dark appearance, with no browser
  console errors. The temporary phone viewport was reset.
- Prepared **9,276 recent stored versions** with excerpt policy v5. Original text
  and raw HTML were preserved. The API, publisher poller and article worker were
  restarted with the updated code; the other local workers remained running.

Machine evidence:

- `.run/audit/pytest-reader-freshness-20261030.xml`
- `.run/audit/reader-freshness-live-20261030.json`
- `.run/audit/reader-snapshot-dates-20261030.json`
- `.run/audit/brief-lifecycle-20261030.json`
- `.run/audit/reader-mobile-dark-20261031.png`
- `.run/audit/reader-mobile-light-20261031.png`
- `.run/audit/latest-news-light-20261031.png`
- `.run/audit/reader-final-20261031.png`
- `.run/audit/ui-reader-verification-20261031.json`
- `.run/audit/runtime-reader-freshness-20261031.txt`

## Practical limits

Coverage depends on connected publishers, successful captures and publisher-supplied
dates. A publication date does not establish factual truth or prove that every
event in a report is new. Topic selection, expiry detection and source-excerpt
selection remain conservative heuristics. This audit verifies the sampled captures
and regression cases, not every historical article or publisher dateline.

Busy periods can sample up to 6,000 reports per request; the UI discloses sampling.
Unknown or weakly captured material can be omitted from the short brief. Publisher
fetching runs independently of Update, which reads the captured archive.
Original source text and archived snapshots are retained; preparing excerpts changes
only derived metadata. No paid API, database migration or cloud deployment was added.
