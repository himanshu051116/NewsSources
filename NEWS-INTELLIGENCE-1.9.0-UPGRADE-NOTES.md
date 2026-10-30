# News Intelligence 1.9.0 — Blind Adjudication & Failure Attribution

## Why this release exists

v1.8 made benchmark accuracy measurable, but its legacy JSONL export still displayed the system prediction and confidence to the human reviewer. That creates anchoring risk: a reviewer may unconsciously converge on the model answer. v1.9 replaces that as the recommended workflow with a prediction-blind, double-review process.

## Blind held-out benchmark workflow

1. `sample` snapshots the current model prediction privately into `verification_benchmark_candidates` using deterministic stratified sampling.
2. `review-sheet` exports article/claim context but deliberately omits `predicted_label` and `predicted_confidence`.
3. Two independent reviewers assess the same cases using pseudonymous reviewer codes. The database stores only SHA-256 reviewer-key fingerprints.
4. `agreement` reports pairwise agreement plus nominal Krippendorff alpha.
5. Cases where the two reviewers disagree are exported via `adjudicator-sheet` to a separate adjudicator.
6. `finalize` only promotes unanimous double-review cases or separately adjudicated disagreements into `verification_benchmark_cases`.
7. The original model prediction used for scoring remains the immutable sampling-time prediction, so the benchmark cannot silently drift if the verifier changes during human review.

## Sampling improvements

Sampling is deterministic for a supplied seed and round-robins across prediction label, language and topic. It initially favors distinct source documents. If train/dev/test samples are created at different times, event groups and source documents already used in another split are excluded from the new split to reduce benchmark leakage.

## Human agreement

The new adjudication layer reports:

- number of multi-review cases;
- unanimous versus disagreement cases;
- pairwise reviewer agreement;
- nominal Krippendorff alpha;
- separately adjudicated disagreement count.

These are measurements of reviewer consistency, not measurements of model correctness.

## Failure attribution

For finalized wrong benchmark verdicts, v1.9 can classify the strongest observable upstream weakness into one of:

- extraction fidelity;
- event identity;
- evidence retrieval;
- evidence independence / lack of primary evidence;
- unresolved conflict handling;
- final verification decision.

This is diagnostic prioritization, not causal proof. The system does not automatically alter verdicts based on the category.

The report also calculates error rates by topic, language and source host to make weak slices visible instead of hiding them inside one global average.

## UI and API

`/accuracy` now includes human-adjudication agreement and a verifier-only diagnostic action.

New endpoints:

- `GET /api/v1/verification-benchmark/{benchmark_set}/agreement`
- `POST /api/v1/verification-benchmark/{benchmark_set}/diagnostics`

The agreement GET is read-only. Persistent agreement snapshots are created by the CLI/finalization workflow rather than as a side effect of viewing the dashboard.

## Database migration

v1.9 adds `0023_blind_adjudication_diagnostics`, creating:

- `verification_benchmark_candidates`
- `verification_benchmark_adjudications`
- `verification_benchmark_agreement_snapshots`
- `verification_benchmark_diagnostic_runs`

The migration is additive and preserves all existing v1.8 data.

## Compatibility

Legacy `verification-benchmark.ps1 -Mode export/import` remains available for existing workflows, but it prints a warning because that path exposes model predictions to reviewers. New held-out benchmarks should use `sample`, `review-sheet`, `review-import`, `agreement`, `adjudicator-sheet`, and `finalize`.

## Validation caveat

Benchmark metrics remain valid only to the extent that the cases, human adjudication and evidence sources are independent and representative. v1.9 improves benchmark methodology; it does not turn benchmark results into a universal factual-accuracy claim.
