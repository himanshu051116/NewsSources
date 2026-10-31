# Accuracy validation program — v1.10.0

v1.10.0 turns the blind-adjudicated benchmark into a repeatable release validation program.

## What is measured

- A content-addressed SHA-256 fingerprint versions the finalized benchmark corpus by adjudicated content rather than only by name.
- Decided-case accuracy is accompanied by a 95% Wilson confidence interval.
- Decision coverage and unsafe high-confidence error rate remain separate from accuracy.
- Language, topic and source slices receive independent gates only after the configured minimum sample size. Smaller slices are marked `insufficient_sample`.
- Active-sampling priorities point the next blind-review batch toward underrepresented, uncertain or failing slices.

## API

`GET /api/v1/verification-benchmark/{benchmark_set}/validation-report`

The default report evaluates the held-out `test` split. Query parameters can adjust `min_overall_cases` and `min_slice_cases` without mutating benchmark data.

## Interpretation

A passing validation report means the configured gates passed on that exact fingerprinted adjudicated corpus. It does not establish universal news accuracy. A changed corpus fingerprint means results should be treated as a new benchmark version even if the human-readable benchmark-set name is unchanged.
