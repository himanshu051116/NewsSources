# Editorial investigation walkthrough — fictional case

**All people, publishers, addresses, documents, incidents and figures in this example are invented.** The file `editorial_review_case.json` is a design and documentation fixture, **not an import file** for the NewsSources database or proof that a live publisher was crawled.

## Question

Two outlets report that **12 riverbank access points** were closed. Does that mean two independent sources confirmed the number?

No. In this example, the outlets quote the **same municipal notice**, so they share one originating information source.

## Evidence trail

| Time (UTC) | Record | What changes |
| --- | --- | --- |
| 09:20 | Northbank Council v1 | Says 12 access points were closed |
| 11:00 | Northbank Gazette | Repeats the v1 figure, attributes it to the council |
| 12:15 | Regional Wire | Also repeats v1; independent corroboration is still zero |
| 15:40 | Northbank Council v2 | Explicit correction: 9, not 12 |

The original 12-point statement must remain visible in version history rather than be erased. Its review state becomes *superseded by source correction*. The 9-point statement has a traceable source but is **not automatically established as an independently confirmed fact**.

## How an analyst should use the application

1. Open an article and inspect its original URL, saved version and capture time.
2. Trace both reports to the originating council notice; do not count them as two independent evidence lineages.
3. Inspect the notice's revision history and link the 12-point claim to the corrected v2 notice.
4. Keep the latest statement in **human review required** until additional sources or verification methods resolve it.
5. Keep the separate footbridge inspection as a different event even though both happened in the same fictional town on the same date.

## What this demonstrates — and what it does not

This case explains *expected editorial behavior* around corrections, claim lineage and event over-merging. It does **not** assert that the current event matcher detects all such cases in production, that the sample JSON conforms to API contracts, or that factual-verification accuracy was measured.

For executable event-link regression tests, see [the constructed event-pair fixture](../backend/tests/fixtures/accuracy/README.md). For evaluation requirements, see [Data provenance and evaluation](../docs/DATA_AND_EVALUATION.md).
