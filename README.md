# NewsSources

**A local news-research workspace for following a story back to its sources.**

A headline is not a complete record of an event. The same report can be republished under several titles, figures change as an incident develops, and a claim repeated by multiple outlets may still trace back to one original statement. NewsSources is an attempt to make those relationships inspectable.

The application collects reporting, preserves article revisions, groups possible reports of the same event, and gives an analyst a place to examine claims alongside their source material and earlier coverage. It is **not** an automatic truth detector or a replacement for editorial judgment.

> **Release status:** `main` contains the v1.25 application. The [reliability changes (PR #1)](https://github.com/himanshu051116/NewsSources/pull/1) and [PDF/OCR work (PR #2)](https://github.com/himanshu051116/NewsSources/pull/2) are draft changes, **not part of this branch**. Passing automated tests is not a newsroom accuracy certificate.

## What the application actually does

| Stage | Output an analyst can inspect | Important limitation |
| --- | --- | --- |
| Source discovery | Publisher registry, feed/sitemap channels and polling records | Discovery is constrained by robots rules, publisher structure and time windows. |
| Article capture | Extracted text, canonical URL, timestamps and immutable article versions | Extracted text can be incomplete; it does not prove the report is true. |
| Event grouping | Candidate same-event links with matching signals | Similar names, places or numbers can cause incorrect merges. |
| Claims and evidence | Claim candidates, source lineage, retrieval attempts and review states | A citation to the originating article is **not independent corroboration**. |
| Historical research | Earlier stored reporting, article revisions and configured archive-provider results | Available history depends on what has been collected or can be retrieved. |
| Analyst workspace | Investigations, saved searches, notes and source-linked briefings | Human review is required before publishing a finding. |

Two editorial rules guide the design: **preserve the original wording** and **make uncertainty visible**. A document location, an extraction-confidence signal and a factual-verification judgment are different things; the interface should not collapse them into one confidence score.

## Try it locally

The documented first-run path targets **Windows, PowerShell, Python 3.12–3.14 and Docker Desktop**.

```powershell
git clone https://github.com/himanshu051116/NewsSources.git
cd NewsSources
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\scripts\run-platform.ps1 start
```

Once the API and workers have started:

- **News reader:** http://127.0.0.1:8010/news
- **Publisher setup:** http://127.0.0.1:8010/news-sources
- **Historical research:** http://127.0.0.1:8010/historical-research
- **API documentation:** http://127.0.0.1:8010/docs

Useful commands:

```powershell
.\scripts\run-platform.ps1 status
.\scripts\services.ps1 doctor
.\scripts\run-platform.ps1 stop
```

This runs local services; it does **not** automatically provide an indexed, verified news corpus. Source onboarding and background extraction must succeed for articles to appear. For first-run troubleshooting, see [Windows setup](SETUP-WINDOWS.md).

## A typical investigation

1. **Add a publisher** using Source Operations and inspect which feed or sitemap channels were actually accepted.
2. **Read the fetched article**, paying attention to source URL, publication time, extraction warnings and whether the article is complete.
3. **Inspect an event dossier** for related reports, then check for duplicates, syndicated reporting and later corrections.
4. **Examine a claim** against its quoted passage, other retrieved evidence and earlier versions; leave it unresolved when evidence is insufficient.
5. **Save the investigation** with notes and references. A generated briefing is a research aid, not a publish-ready fact-check.

An example failure case worth testing: two outlets quote the same press release about a new government policy. Treating the two articles as independent confirmations would overstate the evidence. The lineage model is intended to make this visible; its effectiveness must still be evaluated.

## How the code is organized

```text
backend/src/newsintel/
  adapters/          # fetching, source discovery, HTML extraction, provider integrations
  application/       # article processing, research, search and workspace workflows
  domain/            # event matching, claim/evidence logic, revision and quality rules
  infrastructure/    # SQLAlchemy persistence, database jobs and repositories
  api/               # FastAPI routes and reader pages
  workers/           # poller, articles, enrichment, briefing and background jobs
backend/migrations/  # ordered Alembic schema revisions
backend/tests/       # unit and integration tests; constructed fixtures are identified
config/              # candidate sources for operator-reviewed onboarding
qa/                  # local replay and runtime checks
docs/                # architecture, operating guidance and historical engineering notes
```

PostgreSQL is the canonical structured store. Optional services (object storage, vector search and browser rendering) are configured separately; they should not be confused with required infrastructure for every local run.

## Data is not automatically ground truth

- [Candidate source pack](config/README.md): real publisher URLs included for *manual onboarding review*. Their current response, robots policy, permissions and retention rights are **not certified** by inclusion in a JSON file.
- [Event-pair fixture card](backend/tests/fixtures/accuracy/README.md): 20 **constructed** positive and hard-negative pairs used for regression tests. They are not a labeled news corpus or an independently adjudicated accuracy benchmark.
- [Data and evaluation notes](docs/DATA_AND_EVALUATION.md): what is reproducible, what is illustrative, and what would be needed to claim real-world performance.

These distinctions matter more than an impressive but unsupported accuracy percentage. The evaluation code can calculate metrics; representative ground-truth sets and analyst review must supply the evidence.

## Development checks

After completing local bootstrap:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit
.\.venv\Scripts\python.exe qa/validate_repository_data.py
.\scripts\services.ps1 doctor
```

PostgreSQL integration tests, S3-compatible storage checks, release integrity and container builds run in CI for the relevant development branches. A green CI run shows that its particular checks passed, not that live ingestion or editorial quality is proven.

## Current limitations and work in progress

- Publisher-specific markup changes can reduce extraction quality; review original pages.
- Claims, dates and event identity remain sensitive to ambiguity, conflicting sources and corrections.
- No broad multilingual editorial accuracy claim is established by the constructed regression fixtures.
- Long-term archive completeness and publisher content usage rights need source-by-source checks.
- Production launch requires live ingestion, security, backup/restore and human quality trials.
- Bounded PDF extraction, scanned-document OCR, page-level provenance and related review controls are **proposed in draft PR #2**, not advertised as shipped on `main`.

## Reference material

- [Architecture](docs/ARCHITECTURE.md) · [Acquisition](docs/ACQUISITION_ARCHITECTURE.md) · [Historical providers](docs/HISTORICAL_RESEARCH.md)
- [Deployment runbook](PRODUCTION-RUNBOOK.md) · [Windows setup](SETUP-WINDOWS.md)
- [Engineering review and historical releases](docs/archive/README.md) — earlier audit and version documents are retained as records, not presented as proof of current production readiness.

Maintained in [himanshu051116/NewsSources](https://github.com/himanshu051116/NewsSources). Improvements should include a reproducible case, a test or data example, and a clear statement of what was and was not verified.
