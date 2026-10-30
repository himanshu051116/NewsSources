# Blind adjudication and failure attribution — v1.9.0

News Intelligence separates model predictions from human adjudication so benchmark reviewers are not anchored by the system's answer.

## Recommended held-out workflow

1. Create a deterministic, stratified candidate sample:

```powershell
.\scripts\verification-benchmark.ps1 -Mode sample -BenchmarkSet held-out-v2 -Limit 200 -Seed 20260824
```

2. Export the same blind cases for two independent reviewers. Reviewer keys should be pseudonymous codes, not names or emails:

```powershell
.\scripts\verification-benchmark.ps1 -Mode review-sheet -BenchmarkSet held-out-v2 -ReviewerKey reviewer-a -Path .\review-a.jsonl
.\scripts\verification-benchmark.ps1 -Mode review-sheet -BenchmarkSet held-out-v2 -ReviewerKey reviewer-b -Path .\review-b.jsonl
```

The worksheet intentionally omits `predicted_label` and `predicted_confidence`.

3. Reviewers fill only `adjudicated_label`, `adjudication_source`, and optional notes. Import independently:

```powershell
.\scripts\verification-benchmark.ps1 -Mode review-import -BenchmarkSet held-out-v2 -ReviewerKey reviewer-a -Path .\review-a.jsonl
.\scripts\verification-benchmark.ps1 -Mode review-import -BenchmarkSet held-out-v2 -ReviewerKey reviewer-b -Path .\review-b.jsonl
```

4. Measure human agreement:

```powershell
.\scripts\verification-benchmark.ps1 -Mode agreement -BenchmarkSet held-out-v2
```

The report includes pairwise agreement and nominal Krippendorff alpha. These metrics describe reviewer consistency, not model accuracy.

5. Export only disagreements to a separate adjudicator:

```powershell
.\scripts\verification-benchmark.ps1 -Mode adjudicator-sheet -BenchmarkSet held-out-v2 -ReviewerKey adjudicator-1 -Path .\adjudicate.jsonl
```

After adjudication:

```powershell
.\scripts\verification-benchmark.ps1 -Mode review-import -BenchmarkSet held-out-v2 -ReviewerKey adjudicator-1 -Role adjudicator -Path .\adjudicate.jsonl
```

6. Finalize. Only unanimous double-review cases or separately adjudicated disagreements enter the benchmark table:

```powershell
.\scripts\verification-benchmark.ps1 -Mode finalize -BenchmarkSet held-out-v2
```

7. Run benchmark assessment and diagnostics from `/accuracy` or the API.

## Guardrails

- Reviewer identifiers are stored only as SHA-256 hashes; use pseudonymous reviewer codes.
- The model prediction is snapshotted privately at sampling time and cannot drift during review.
- A single review cannot finalize a new benchmark case.
- Reviewer disagreements are not resolved by majority guessing; they require a separate adjudicator.
- Failure attribution is diagnostic, not causal proof. It prioritizes likely upstream weaknesses for engineering review.
- Extraction fidelity, event-link accuracy, and factual-verification accuracy remain separate metrics.
