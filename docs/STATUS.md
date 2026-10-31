# Project status and next steps

_Last editorial status review: 31 October 2026. This is a repository-state summary, not a production readiness certificate._

## What is on `main`

The default branch is the v1.25 application. It includes a local reader, publisher/feed discovery, article versioning, event candidates, claim and evidence review, historical lookup, workspace features, and background processing workers. These are implemented modules; they do not imply a populated production news archive or independently measured factual accuracy.

- **Usable entry points:** `/news`, `/news-sources`, `/historical-research`, `/docs` on the local API (see [Windows setup](../SETUP-WINDOWS.md)).
- **Primary datastore:** PostgreSQL. Optional configurations add object storage, vector retrieval and isolated browser rendering.
- **Development posture:** extensive automated tests and local QA workflows exist, but live acceptance and representative editorial benchmarking remain separate requirements.

## Proposed changes under review

| Change | Branch / review | Shipping status |
| --- | --- | --- |
| Evidence storage integrity, revision history and reproducible CI | [PR #1](https://github.com/himanshu051116/NewsSources/pull/1) | Draft, not merged into `main` |
| PDF acquisition, page provenance, optional English/Hindi OCR and review flags | [PR #2](https://github.com/himanshu051116/NewsSources/pull/2) | Draft, depends on PR #1 |
| Engineering-facing repository presentation, source/fixture provenance and examples | [PR #3](https://github.com/himanshu051116/NewsSources/pull/3) | Draft, depends on PR #1 |

Do not equate a green test run on a draft feature branch with the functionality present on `main`.

## Work still needed for a credible newsroom pilot

1. **Publisher trials:** explicitly approved sources, rights and retention decisions, feed availability, publication-to-capture latency, article completeness, retry behavior and failure rates.
2. **Editorial evaluation:** independently labeled same-event and different-event pairs, source-lineage conflicts, version corrections and source-location checks. The bundled 20 event pairs are constructed regression cases only.
3. **PDF/OCR validation:** independently transcribed English/Hindi documents and scanned pages, table/citation adjudication and isolation tests for hostile PDFs before enabling wider PDF acquisition.
4. **Operations:** production auth, backups and restore drill, durable storage, incident runbook, observability and extended acceptance runs.
5. **Reader review:** accessibility, mobile/browser usability, correction visibility and explicit separation of extraction confidence from factual verification.

## Where evidence belongs

- [Data provenance and evaluation](DATA_AND_EVALUATION.md)
- [Fictional editor walkthrough](../examples/README.md)
- [Production runbook and acceptance procedure](../PRODUCTION-RUNBOOK.md)
- [Older 12 October 2026 planning assessment](archive/reviews/2026-10-12-platform-assessment.md)

When the project crosses a gate, update this file with a dated link to a reproducible test, human evaluation or deployment record. Avoid replacing measurements with broad production-readiness statements.
