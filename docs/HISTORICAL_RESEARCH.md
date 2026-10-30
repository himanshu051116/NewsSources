# Historical Research Providers

The historical research module combines multiple providers instead of treating a single
news API as complete evidence. It returns provider-specific status, isolates failures,
deduplicates canonical URLs, and never sends configured API keys to the browser.

## Security rule

Do not commit real keys. Put them in a local `.env` file or a deployment secret store.
The repository contains empty placeholders only.

## Provider matrix

| Provider | Key | Best use | Important limitation |
|---|---|---|---|
| GDELT DOC API | No | Global, multilingual discovery and recent narrative comparison | The DOC endpoint supports only approximately the latest three months. Requests outside that range return an explicit `unsupported_date_range` status. |
| Guardian Open Platform | Yes | Deep Guardian archive search, article metadata and text under the selected access terms | The free developer key is for non-commercial use and has usage limits. |
| New York Times Article Search | Yes | NYT archive discovery by keyword and date | Access, quotas and permitted use are controlled by NYT terms. The connector intentionally requests only metadata and snippets. |
| NewsAPI | Yes | Development-time comparison across its indexed publishers | The free developer plan is development/testing only, delayed, and limited to recent articles. Do not enable it as a production dependency. |
| Google Fact Check Tools | Yes | Finding published ClaimReview records related to a claim | Results are prior fact checks, not independent proof that the current claim is true or false. |
| Internet Archive Wayback | No | Finding a nearest archived copy of a known URL | Availability varies by site, date and archive policy. |
| Common Crawl | No | Locating captures of a known URL across recent crawl indexes | The index is not a topic-search news API. Respect index-server load guidance and use bulk datasets for large analysis. |

## Configuration

```env
NEWSINTEL_HISTORICAL_SEARCH_ENABLED=true
NEWSINTEL_HISTORICAL_PROVIDER_TIMEOUT_SECONDS=15
NEWSINTEL_HISTORICAL_PROVIDER_MAX_RESULTS=100
NEWSINTEL_COMMON_CRAWL_COLLECTION_COUNT=3

NEWSINTEL_GUARDIAN_API_KEY=
NEWSINTEL_NEW_YORK_TIMES_API_KEY=
NEWSINTEL_NEWS_API_KEY=
NEWSINTEL_GOOGLE_FACT_CHECK_API_KEY=
```

Keyless providers work without registration. Key-backed providers remain visible in
provider status as `not_configured` until their secret is set.

## API

### Search historical news and fact checks

```http
POST /api/v1/historical/search
Content-Type: application/json
```

```json
{
  "query": "climate finance India",
  "from_date": "2026-05-01",
  "to_date": "2026-07-20",
  "language": "en",
  "providers": ["gdelt", "guardian", "google_fact_check"],
  "limit": 50
}
```

The response contains:

- deduplicated results;
- the provider that produced every record;
- a provider status for success, timeout, missing configuration or unsupported date range;
- the number of duplicates collapsed;
- no API key or credential material.

### Find archived versions of a known URL

```http
POST /api/v1/historical/archives/lookup
Content-Type: application/json
```

```json
{
  "url": "https://example.com/news/story",
  "timestamp": "2024-01-10T00:00:00Z",
  "providers": ["wayback", "common_crawl"],
  "limit": 20
}
```

## User interface

Approved analyst accounts can open:

```text
http://127.0.0.1:8010/historical-research
```

The page renders all external values through DOM `textContent`, validates external URL
schemes, and opens links with `noopener noreferrer`.

## Evidence interpretation

Historical search results are discovery records, not final verification. Before a result
supports an assessment, the platform still needs to:

1. fetch and preserve the exact source version;
2. identify whether it is primary, secondary, syndicated or circular;
3. extract an exact supporting or contradicting passage;
4. record publication and retrieval times;
5. apply a versioned evidence policy;
6. abstain when evidence is insufficient or not independent.

## v0.5.0 temporal knowledge additions

Historical analysis now includes internal, evidence-preserving temporal intelligence in addition
to provider search. The platform can reconstruct **as-known-then** event snapshots from article
versions, claim-verification revisions and commitment outcomes available by a selected timestamp.
It can also expose claim confidence histories and track evidence-scoped commitments/outcomes.
These views deliberately separate publication/observation time from later evidence so later facts
do not silently leak into earlier historical states.

Primary-record planning and passage evaluation are durable: evidence-search runs, exact evidence
passages, temporal relations, authority-registry validation and resulting verification revisions can
be audited later. External historical providers remain supplementary discovery inputs rather than
the sole historical memory of the system.


## v0.6.0 temporal graph additions

Historical intelligence can now be materialized as a time-bounded event knowledge graph containing event, claim, entity, actor, commitment, evidence and verification-revision nodes. Each evidence or verification revision retains its own observation time so an `as_of` query does not leak later knowledge into an earlier snapshot.

The graph-diff endpoint compares two timestamps and reports nodes/relationships that appeared or expired between them. This complements the v0.5 knowledge-snapshot API by providing an explicit relationship model for questions such as what evidence arrived, which verification changed, and what commitments became known during a time interval.

Publisher/topic reliability snapshots are also retained historically. They are descriptive context derived from adjudicated claims and are deliberately excluded from the current article evidence-readiness score.
