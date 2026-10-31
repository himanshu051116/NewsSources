# Documentation guide

Use the live [project status](STATUS.md) to see which parts of NewsSources are shipped on `main` and which are still in draft branches. Older engineering notes record design decisions at the time they were written; they are **not** the current release contract.

| Question | Start here |
| --- | --- |
| What is built, and what is not? | [Current project status](STATUS.md) |
| How do articles reach the database? | [Acquisition architecture](ACQUISITION_ARCHITECTURE.md) |
| Why is an article grouped with an event? | [Event identity and evidence architecture](EVENT_INTELLIGENCE_ARCHITECTURE.md) |
| What stores article revisions and lineage? | [System architecture](ARCHITECTURE.md) |
| How do analysts compare earlier reporting? | [Historical research providers](HISTORICAL_RESEARCH.md) |
| How are briefings assembled? | [Daily and weekly briefs](NEWS_DIGESTS.md) |
| Which data are real, synthetic or unverified? | [Data provenance and evaluation](DATA_AND_EVALUATION.md) |
| How do I run or recover the application? | [Windows setup](../SETUP-WINDOWS.md) and [Production runbook](../PRODUCTION-RUNBOOK.md) |

## Technical design and implementation

- [Implementation plan](IMPLEMENTATION_PLAN.md) and [implementation guardrails](IMPLEMENTATION_GUARDRAILS.md) are long-form engineering references, not short quickstarts.
- [Module synchronization contract](MODULE_SYNCHRONIZATION.md) records ownership between modules.
- [Local AI strategy](LOCAL_AI_STRATEGY.md) describes optional locally hosted model features; do not assume these are enabled by default.
- [Fictional editorial walkthrough](../examples/README.md) demonstrates correction handling and shared-source reporting without pretending to contain verified news.
- [Historical release and QA archive](archive/README.md) retains prior audit reports.
- [Historical implementation notes](archive/implementation/) are grouped by version and technical subject, rather than promoted as current features.

## What counts as verification?

A passing unit test proves a code path behaved as asserted on its test inputs. A publisher's original paragraph establishes the **origin** of a statement, not its factual truth. A collection of synthetic event pairs checks regressions, not newsroom accuracy.

A credible claim about real-world behavior needs versioned examples, permissioned source captures, reproducible commands, and an independently reviewed evaluation. See [Data and evaluation](DATA_AND_EVALUATION.md) for the provenance rules and remaining work.
