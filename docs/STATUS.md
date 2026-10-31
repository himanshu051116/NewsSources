# Project status

**Repository check: 31 October 2026.** This page describes the code on `main`, not the operational state of any deployed instance.

## Merged work

The package identifies itself as `1.25.0` in `pyproject.toml`. The following development changes were merged into `main` on 31 October 2026; merging them did not deploy a production service or independently establish newsroom accuracy.

| Work | Merged review |
| --- | --- |
| Artifact persistence, source-lineage safeguards, revision-history checks and reproducible CI | [PR #1](https://github.com/himanshu051116/NewsSources/pull/1) |
| Bounded PDF text extraction, opt-in English/Hindi OCR, source-page references and review-only tables | [PR #2](https://github.com/himanshu051116/NewsSources/pull/2) |
| README, publisher-review metadata, fixture provenance and archived engineering notes | [PR #3](https://github.com/himanshu051116/NewsSources/pull/3) |
| Technical documentation index and implementation-history archive | [PR #4](https://github.com/himanshu051116/NewsSources/pull/4) |
| Permissioned event-pair corpus admission and integrity checks | [PR #5](https://github.com/himanshu051116/NewsSources/pull/5) |

**Verification:** the merge head `757423bea3463d74df7e98db05b7c55bf04e855c` passed the [GitHub Actions workflow on `main`](https://github.com/himanshu051116/NewsSources/actions/runs/41177697695) (Linux/PostgreSQL, Windows, S3-compatible persistence and Docker build). These tests cover the checked code paths, not live publisher performance.

## Local entry points

- Reader: `http://127.0.0.1:8010/news`
- Source operations: `http://127.0.0.1:8010/news-sources`
- Historical research: `http://127.0.0.1:8010/historical-research`
- FastAPI documentation: `http://127.0.0.1:8010/docs`

See [Windows setup](../SETUP-WINDOWS.md) for local start/stop instructions.

## Not yet established

- **Publisher operations:** approved source terms and retention, measured feed availability, capture latency and article completeness.
- **Editorial quality:** independently labeled event pairs, citation correctness, corrections, abstention behavior and review of shared-source claims.
- **PDF/OCR performance:** accuracy on varied scanned English/Hindi pages, tables, damaged PDFs and verified page anchors.
- **Operational readiness:** authentication, access reviews, backup/restore drills, security controls, observability and live-source acceptance trials.
- **Production deployment:** no deployment is inferred from a merge or a passing CI run.

## Reference material

[Data and evaluation](DATA_AND_EVALUATION.md) · [Event corpus protocol](EVENT_CORPUS_WORKFLOW.md) · [Fictional editorial case](../examples/README.md) · [Runbook](../PRODUCTION-RUNBOOK.md) · [Historical assessment](archive/reviews/2026-10-12-platform-assessment.md)
