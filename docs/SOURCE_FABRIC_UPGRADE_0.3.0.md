# Source Fabric Upgrade — 0.3.0

## Goal

Release 0.3.0 upgrades publisher acquisition from a small deterministic RSS/sitemap
bootstrap into a broader, policy-aware and measurable **Source Fabric** while preserving the
existing frontier, polling and article-processing contracts.

The release intentionally separates **discovery** from **authorization**: newly observed
external domains are quarantined as candidates and are never silently activated for crawling.

## Implemented in this release

### 1. Syndication discovery

- RSS and Atom remain supported.
- JSON Feed 1.0 and 1.1 are parsed, validated and pollable through the same acquisition
  contract.
- HTML `link[rel=alternate]` discovery recognizes RSS, Atom and `application/feed+json`.
- HTTP `Link` response headers are inspected for advertised syndication endpoints.
- Feed validation preserves WebSub hub and self-link metadata in channel configuration.
- Common endpoint probing now includes additional RSS/Atom/JSON Feed and sitemap variants.

### 2. News Sitemap and sitemap intelligence

- Google News Sitemap documents are detected from XML content/namespace evidence and are
  represented as `news_sitemap` rather than ordinary sitemap channels.
- A generic sitemap channel can self-correct to `news_sitemap` after polling proves its
  payload contains News Sitemap records; the detected type is persisted.
- News publication name, language, publication date and title are extracted when present.
- gzip-compressed sitemap payloads are supported with a decompressed-size safety limit.
- Sitemap-index expansion preserves a News Sitemap parent hint while generic indexes stay
  generic until child content is inspected.

### 3. Homepage, section and structured-data discovery

- Homepage endpoint discovery merges evidence instead of discarding duplicate endpoint hints.
- Listing/section discovery uses scored URL and navigation-label evidence rather than a small
  fixed English path allow-list.
- High-value paths such as latest, national, international, states, cities, elections,
  finance, markets, science and technology receive discovery evidence.
- Initial Hindi navigation labels are recognized.
- `Article`, `NewsArticle`, `ReportageNewsArticle`, `AnalysisNewsArticle` and `BlogPosting`
  JSON-LD can contribute article URLs, titles and `datePublished` values.
- Structured article evidence can admit short/opaque article URLs that URL-shape heuristics
  alone would miss, while feed/media/document assets remain rejected and recency checks still
  apply.

### 4. Robots-aware crawl policy and per-host safety

- `RobotsPolicy` parses user-agent groups and Allow/Disallow rules with longest-match
  precedence, `*` wildcards and `$` end anchors.
- `CrawlPolicyHttpFetcher` checks robots policy before ordinary source/article requests.
- Robots responses are cached by origin.
- Transient robots failures can fail closed (default) or fail open by configuration.
- `HostRequestBudget` adds process-local per-host concurrency and minimum request spacing.
- New environment settings expose robots/cache/host-budget behavior without changing worker
  call sites.

### 5. Publisher source registry and policy provenance

Alembic revision `0011_source_fabric_registry` adds:

- `publisher_domains` for durable publisher-domain/edition/locale foundations;
- `robots_snapshots` for timestamped policy provenance;
- `source_candidates` for quarantined source-expansion candidates.

Publisher onboarding now persists the primary publisher domain and a robots snapshot while
retaining the original `publishers.canonical_domain` field for backward compatibility.

### 6. Source health and coverage observability

A deterministic channel-health policy now scores channels from:

- successful/not-modified/failed polls;
- observation yield;
- recency of successful polling;
- consecutive failures.

New API:

- `GET /publishers/{publisher_id}/source-health?window_hours=24`

The discovery-audit layer measures:

- candidates observed per channel;
- candidates unique to one channel;
- overlap between channels;
- first-discovery wins;
- unique-contribution and first-discovery rates.

New API:

- `GET /publishers/{publisher_id}/discovery-audit?window_hours=24`

This is the foundation for later empirical scheduling and recall measurement.

### 7. Safe source self-expansion foundation

Article extraction now retains a bounded set of high-value external links while filtering
same-site links and common social/share infrastructure. Article persistence reduces those
links to external origins and upserts them as `source_candidates` with accumulating evidence.

Candidates remain in `quarantined` state with the explicit activation policy
`manual_or_validated_probe_required`. Observation never authorizes crawling.

New API:

- `GET /source-candidates?state=quarantined&limit=100`

### 8. Repository integrity repair

The 0.2.0 archive referenced raw-artifact adapters that were absent. 0.3.0 restores:

- `LocalRawArtifactStore` with atomic local writes;
- `S3RawArtifactStore`;
- `_is_missing_object_error`, used by the existing S3 tests.

This restores the source files expected by the article worker and artifact-store tests.

## Configuration added

The `.env.example` now exposes:

```text
NEWSINTEL_CRAWLER_ROBOTS_ENABLED=true
NEWSINTEL_CRAWLER_ROBOTS_CACHE_SECONDS=3600
NEWSINTEL_CRAWLER_FAIL_CLOSED_ON_ROBOTS_ERROR=true
NEWSINTEL_CRAWLER_MAX_CONCURRENT_PER_HOST=2
NEWSINTEL_CRAWLER_MIN_HOST_INTERVAL_SECONDS=0.25
```

## Validation performed

The final source-focused regression set contains **63 passing tests** covering:

- RSS, Atom and JSON Feed;
- ordinary, News and gzip sitemaps;
- HTML/HTTP endpoint discovery;
- multilingual listing discovery;
- JSON-LD article discovery and trusted-evidence admission;
- recent-article URL filtering;
- channel polling and dynamic News Sitemap detection;
- robots policy and host request budgeting;
- source health and discovery-audit calculations;
- article extraction/external-link filtering;
- local and S3 raw-artifact adapters.

Python compilation also succeeds for `backend/src`, `backend/tests` and migrations.

A fresh `uv sync --frozen --extra dev` was attempted but could not download packages because
DNS/network access is disabled in the execution sandbox. The preinstalled Python environment
also lacks `structlog`, so the entire repository test suite cannot be collected there.
`structlog` remains declared in the package dependency manifest; this is an environment
validation limitation, not a removed project dependency.

## Deliberately deferred

0.3.0 is a major source-layer upgrade, but it does not claim that global recall is solved.
The next Source Fabric milestones should be versioned separately:

1. distributed host budgets shared across worker processes;
2. robots re-validation across cross-origin redirect hops;
3. complete publisher edition/locale ownership resolution;
4. WebSub subscriber/callback/lease lifecycle, not only hub discovery;
5. validated candidate probing and explicit candidate approval workflow;
6. independent recall audits using provider/archive gap signals;
7. empirical scheduling based on publisher velocity and channel contribution;
8. benchmark-backed multilingual source-discovery expansion;
9. source-candidate evidence tables rather than only aggregate evidence counters;
10. automated strategy proposals that remain reviewable and non-self-authorizing.
