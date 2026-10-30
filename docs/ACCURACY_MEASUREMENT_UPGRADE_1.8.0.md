# Accuracy Measurement & Adjudication Upgrade 1.8.0

Version 1.8.0 turns accuracy checking into an explicit, reproducible workflow rather than a collection of successful examples.

## Design rule: do not blend unlike accuracy concepts

The platform reports three different dimensions separately:

- **publisher-page extraction fidelity** — reproduction of what the publisher page actually contained;
- **event-link accuracy** — precision/recall for joining reports that refer to the same real-world event;
- **claim-verification accuracy and coverage** — correctness of substantive verification decisions on a human-adjudicated benchmark.

None of these metrics by itself is a universal "news truth" score.

## Verification benchmark v3

The verification benchmark keeps the existing all-case metrics and adds decision-aware metrics:

- decision coverage;
- abstention rate;
- decided-case accuracy;
- decided-case macro F1;
- unsafe high-confidence error rate.

`not_checkable` is treated as an abstention for decision metrics. This means a responsible refusal to decide does not count as a false factual verdict, but excessive abstention still reduces coverage.

The release quality gate can enforce minimum decision coverage and decided-case accuracy and a maximum unsafe high-confidence error rate.

Confidence calibration is also evaluated only on substantive verdicts. Abstention behaviour is measured separately through coverage.

## Human adjudication workflow

Export a balanced sample of real extracted claims:

```powershell
.\scripts\verification-benchmark.ps1 -Mode export -Path .\verification-benchmark.jsonl -Limit 200
```

The JSONL contains the system's current prediction/confidence plus article/event/source metadata and blank adjudication fields. A reviewer supplies at least:

- `adjudicated_label`;
- `adjudication_source`.

Then import the reviewed cases into a held-out set:

```powershell
.\scripts\verification-benchmark.ps1 -Mode import -Path .\verification-benchmark.jsonl -BenchmarkSet local-held-out-v1 -Split test
```

The existing benchmark assessment, corpus audit and quality-gate APIs can then evaluate that set. `/accuracy` provides a human-facing analyst view.

## Event-link regression benchmark

The event-link benchmark now contains 20 adjudicated positive and hard-negative pairs spanning maritime incidents, earthquakes, monetary policy, technology, sports, courts, fires, floods and multilingual paraphrases.

Run it with:

```powershell
.\scripts\event-benchmark.ps1 -Json
```

The benchmark reports precision, recall, F1, false-link/false-miss rates, score distributions and threshold margins. It is a regression gate only; its score must not be presented as global event-detection accuracy.

The structured lexical matcher remains intentionally explainable and is now methodology version `event-matching-structured-lexical-v4`. It fixes short-location substring errors, reduces generic-entity anchors, handles disjoint specific locations more conservatively, retains numeric identifiers and gates strong-anchor bonuses behind article-specific evidence.

## Extraction fidelity aggregation

The live accuracy audit can now summarize multiple publisher URLs:

```powershell
.\scripts\accuracy-audit.ps1 -Url "https://publisher.example/a" -Url "https://publisher.example/b" -Summary -Json
```

The aggregate report includes HTTP/extraction success, measurable fidelity rate, mean/min fidelity, threshold pass rate, label counts and common discrepancies. Extraction fidelity means reproduction of the publisher page, not factual correctness of the underlying report.

## Analyst accuracy workspace

`/accuracy` presents:

- all-case versus decided-case metrics;
- decision coverage / abstention;
- macro F1;
- unsafe high-confidence error rate;
- corpus split leakage/readiness;
- release quality-gate state;
- benchmark history.

Older benchmark rows created before v1.8 show decision metrics as not measured rather than incorrectly displaying zero coverage.

## Guardrails

- Do not publish a universal accuracy percentage from the included small regression fixtures.
- Keep benchmark test cases held out from heuristic/model tuning where possible.
- Treat benchmark leakage as a release-blocking data-quality problem.
- Keep extraction fidelity, event linking and factual verification metrics separate.
- Treat abstention as coverage loss, not as a false verdict.
- Treat confident wrong substantive verdicts as especially serious.
