# Historical Enrichment Upgrade 1.1.0

Version 1.1.0 integrates historical analysis into the normal news-extraction lifecycle.

## Core change

Every successfully committed article version now creates exactly one durable historical-enrichment job in the same transaction. A separate worker enriches the version after commit, so article visibility is not blocked by historical-provider latency or outages.

The worker gathers:

- earlier versions of the same article;
- prior articles already assigned to the same event;
- prior claims with the same claim-family identity;
- the latest stored verification state for those prior claims;
- related internal-corpus articles ranked by deterministic lexical overlap;
- bounded historical-provider results when external enrichment is enabled;
- timeline span and earliest/latest prior observations;
- new vs recurring claim families;
- changed claim families;
- numeric and temporal changes between current and prior claim-family members.

Automatic enrichment uses the current article version's `retrieved_at` as its knowledge cutoff. Results known only after that cutoff are not automatically included as historical evidence.

## Extraction fix

Publicly visible text is no longer discarded solely because subscription/paywall boilerplate is detected. Such content is stored with a `partial` processing stage and extraction warnings. No paywall bypass or hidden-content retrieval is implemented.

## Existing databases

The worker idempotently queues historical-enrichment jobs for older article versions that predate this release. Do not delete your existing database and do not re-fetch all publishers merely to obtain historical context.

## New schema

Alembic head: `0018_historical_enrichment`

New tables:

- `article_historical_enrichment_jobs`
- `article_historical_contexts`

## New API behavior

- article summaries expose `historical_context_status`;
- article detail embeds the latest historical context and enrichment-job state;
- `GET /api/v1/articles/{article_id}/historical-context` returns the context directly;
- `/api/v1/status` and Prometheus metrics expose historical queue/failure/context counts.

## New worker

```text
newsintel-historical-enrichment
```

The Windows `run-platform.ps1 start` command launches it automatically.

## Upgrade existing local installation

After replacing the source with 1.1.0:

```powershell
.\scripts\bootstrap.ps1
.\scripts\services.ps1 migrate
.\scripts\services.ps1 doctor
.\scripts\run-platform.ps1 restart
```

Then check:

```powershell
.\scripts\run-platform.ps1 status
Get-Content .run\logs\historical.out.log -Tail 100
```

The dashboard will show `history queued/running/internal_only/complete/partial/failed` for article cards.
