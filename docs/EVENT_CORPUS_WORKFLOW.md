# Event-link evaluation corpus: capture and review

NewsSources has an event-link scorer (`newsintel-event-benchmark`) and constructed regression pairs. This workflow adds an **offline admission gate** before an evaluator exports cases for scoring. It does not fetch news, approve content rights or establish factual truth.

## Required local evidence

Keep a JSON manifest and permissioned UTF-8 article captures in a private working directory. For each article pair record the original HTTPS URL, headline, timezone-aware capture timestamp, SHA-256 of the exact UTF-8 capture, original information-lineage key, event-group key, and train/dev/test split. Store two independent reviewer labels (`same` or `different`) and, on disagreement, an independent adjudicator. For real captures, also record a rights contact and per-capture local-evaluation approval.

A lineage key identifies the *underlying bulletin or wire*, not merely the publisher's domain. Different sites repeating a single press release can share the same lineage. Cross-split event groups, content hashes and information lineages are rejected.

## Private files

Use `evaluation/private/event-pairs.json`, `evaluation/private/captures/*.txt`, and `evaluation/results/` for reports and exported pairs. Those directories are Git-ignored by the accompanying change. Do not commit restricted publisher text or private reviewer identifiers.

## Commands

Audit the manifest without exporting any source text:

```bash
python qa/editorial_benchmark.py --manifest evaluation/private/event-pairs.json --report evaluation/results/admission-report.json
```

After admission, export an input to the existing event matcher:

```bash
python qa/editorial_benchmark.py --manifest evaluation/private/event-pairs.json --split test --export evaluation/results/event-pairs-for-benchmark.json
newsintel-event-benchmark --input evaluation/results/event-pairs-for-benchmark.json --json > evaluation/results/event-scoring.json
```

The exported file contains captured article texts: keep it private and respect source rights. The exporter refuses overwrites, avoids clobbering its input manifest, and restricts real-source exports inside the repository to the ignored `evaluation/results/` directory. A metadata-only report records the manifest and export SHA-256 hashes, but does not certify factual accuracy or publication rights. The gate audits **all manifest cases** for leakage, but `--split test` exports only held-out cases. The existing scorer consumes all exported cases, so never report unfiltered train/dev/test results as held-out accuracy.

Run a fictional smoke test (not real-world performance):

```bash
python qa/editorial_benchmark.py --manifest examples/synthetic_event_pair_manifest.json --allow-synthetic-export --export evaluation/results/synthetic-smoke.json
```

## Manifest contract

The [synthetic example](../examples/synthetic_event_pair_manifest.json) demonstrates field names and intentionally uses reserved `.example` URLs and invented reviewers. A real manifest must set `dataset_kind: "real"`, `protocol_version: "event-pair-review-v1"` and a `rights_contact`. Each capture must use local relative `text_path` rather than inlined text and declare `rights_review: "approved_for_local_evaluation"`.

The audit verifies exact local capture hashes, reviewer separation, independent adjudication of disagreements, safe paths, unique IDs and absence of cross-split event/capture/lineage reuse. It is metadata validation, not a legal or factual investigation.

## What passing means

Passing means **the supplied metadata and local capture hashes are internally consistent**. It cannot prove that distinct reviewer IDs represent real distinct people, that the publisher permitted use, that a URL was actually fetched, or that a dataset is representative. Report event grouping, extraction fidelity, source-location accuracy, factual judgments and abstention separately. Do not attach a real-world accuracy claim to the fictional sample.
