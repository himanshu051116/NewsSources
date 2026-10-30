# Automatic Historical Enrichment 1.1.0

**Release:** 1.1.0  
**Schema head:** `0018_historical_enrichment`

Version 1.1.0 makes historical analysis part of normal article ingestion rather than a separate analyst-only search flow.

## Processing contract

A new immutable article version is committed first. In the same transaction, the platform creates one durable historical-enrichment job for that version. A separate worker processes the job asynchronously, so slow or unavailable historical providers cannot prevent the article from appearing in the platform.

```text
source discovery
  -> article fetch
  -> visible-text extraction
  -> immutable article/version + atomic claims COMMIT
  -> durable historical-enrichment job
  -> same-event and previous-version history
  -> prior claim-family history
  -> internal corpus similarity
  -> external historical providers (bounded and optional at runtime)
  -> claim-evolution analysis
  -> persisted article historical context
```

## Time semantics

Automatic enrichment uses the current version's `retrieved_at` value as its cutoff. It only treats content published/observed before that cutoff as historical context. External results without a usable publication timestamp are not automatically asserted as historical.

This preserves the distinction between:

- when the article was published;
- when News Intelligence observed a version;
- what evidence existed before that observation;
- later retrospective research requested explicitly by an analyst.

## Historical context attached to each article

The persisted context includes:

- prior articles assigned to the same event;
- prior versions of the same article;
- prior claims sharing the same claim-family key;
- previous verification label/confidence when available;
- internally stored related articles ranked by deterministic lexical overlap;
- bounded external historical-provider results;
- provider success/failure status;
- earliest/latest prior observations and historical span;
- counts of new, recurring, changed, numeric-change and temporal-change claim families;
- a bounded `claim_evolution` list showing the current claim and the most recent prior family member.

Historical context is deliberately descriptive evidence. Graph proximity, lexical similarity, common claim families, or old reporting never establish truth by themselves.

## Extraction quality behavior

The article processor no longer rejects otherwise usable public text merely because the page contains subscription/paywall boilerplate indicators. Such content is persisted as `partial` with warnings. The platform does not bypass paywalls and does not attempt to recover hidden subscriber-only text.

## Backfill

The historical-enrichment worker automatically creates missing jobs for versions ingested before 1.1.0. Upgrading an existing local database therefore does not require deleting or re-fetching articles.

## Worker

Entry point:

```text
newsintel-historical-enrichment
```

or:

```text
python -m newsintel.workers.historical_enrichment
```

The Windows `run-platform.ps1` script starts/stops/status-checks this worker alongside the API, poller, article worker and outbox worker.

## API

Article summaries expose `historical_context_status`.

`GET /api/v1/articles/{article_id}` includes the latest persisted historical context plus enrichment-job state.

`GET /api/v1/articles/{article_id}/historical-context` returns the current historical context directly.

## Configuration

```env
NEWSINTEL_HISTORICAL_ENRICHMENT_ENABLED=true
NEWSINTEL_HISTORICAL_ENRICHMENT_EXTERNAL_ENABLED=true
NEWSINTEL_HISTORICAL_ENRICHMENT_BATCH_SIZE=10
NEWSINTEL_HISTORICAL_ENRICHMENT_CONCURRENCY=2
NEWSINTEL_HISTORICAL_ENRICHMENT_LEASE_SECONDS=300
NEWSINTEL_HISTORICAL_ENRICHMENT_IDLE_SECONDS=2
NEWSINTEL_HISTORICAL_ENRICHMENT_MAX_ATTEMPTS=3
NEWSINTEL_HISTORICAL_ENRICHMENT_MAX_QUERIES=3
NEWSINTEL_HISTORICAL_ENRICHMENT_INTERNAL_LIMIT=25
NEWSINTEL_HISTORICAL_ENRICHMENT_EXTERNAL_LIMIT_PER_QUERY=15
```

External retrieval is asynchronous. Internal event/corpus history still persists if external providers are unavailable.
