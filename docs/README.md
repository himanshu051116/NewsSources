# Documentation guide

Use [project status](STATUS.md) for the features currently merged into `main` and the remaining evaluation work. Older engineering notes record design decisions at the time they were written; they are **not** the current release contract.

| Question | Start here |
| --- | --- |
| What is built, and what is not? | [Current project status](STATUS.md) |
| What is the end-to-end data flow? | [Pipeline overview](PIPELINE_OVERVIEW.md) |
| How do articles reach the database? | [Acquisition architecture](ACQUISITION_ARCHITECTURE.md) |
| Why is an article grouped with an event? | [Event identity and evidence architecture](EVENT_INTELLIGENCE_ARCHITECTURE.md) |
| What modules and services are in the current code? | [Implemented architecture](IMPLEMENTED_ARCHITECTURE.md) |
| What was originally proposed? | [June 2026 architecture proposal](ARCHITECTURE.md) |
| How do analysts compare earlier reporting? | [Historical research providers](HISTORICAL_RESEARCH.md) |
| How are briefings assembled? | [Daily and weekly briefs](NEWS_DIGESTS.md) |
| Which data are real, synthetic or unverified? | [Data provenance and evaluation](DATA_AND_EVALUATION.md) |
| How can a real event-pair corpus be admitted for evaluation? | [Offline corpus and independent-review workflow](EVENT_CORPUS_WORKFLOW.md) |
| How do I run or recover the application? | [Windows setup](../SETUP-WINDOWS.md) and [Production runbook](../PRODUCTION-RUNBOOK.md) |

## Technical design and implementation

- [Implemented architecture](IMPLEMENTED_ARCHITECTURE.md) maps the checked-in application to real source files; [the older design proposal](ARCHITECTURE.md) includes aspirational components that should not be mistaken for current dependencies.
- [Implementation plan](IMPLEMENTATION_PLAN.md) and [implementation guardrails](IMPLEMENTATION_GUARDRAILS.md) are long-form engineering references, not short quickstarts.
- [Module synchronization contract](MODULE_SYNCHRONIZATION.md) records ownership between modules.
- [Local AI strategy](LOCAL_AI_STRATEGY.md) describes optional locally hosted model features; do not assume these are enabled by default.
- [Fictional editorial walkthrough](../examples/README.md) demonstrates correction handling and shared-source reporting without pretending to contain verified news.
- [Historical release and QA archive](archive/README.md) retains prior audit reports.
- [Historical implementation notes](archive/README.md) are grouped by version and technical subject, rather than promoted as current features.

## What counts as verification?

A passing unit test proves a code path behaved as asserted on its test inputs. A publisher's original paragraph establishes the **origin** of a statement, not its factual truth. A collection of synthetic event pairs checks regressions, not newsroom accuracy.

A credible claim about real-world behavior needs versioned examples, permissioned source captures, reproducible commands, and an independently reviewed evaluation. See [Data and evaluation](DATA_AND_EVALUATION.md) for the provenance rules and remaining work.
