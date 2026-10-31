# Event-pair regression cases

`event_pairs.json` is a **constructed test fixture** with 20 paired report-like examples: 10 marked `same`, 10 marked `different`. It targets event grouping heuristics, including near-duplicate wording, temporal follow-ups, Hindi reporting and misleading overlap across unrelated events.

It is **not** a download of publisher articles, an independently labeled newsroom corpus, or a benchmark of factual truth. Some details resemble real-world reporting; do not infer that the incident facts were verified. The `case_origin` and `fact_verification` fields are metadata; the existing event-matching test still consumes `label`, `left_title`, `left_text`, `right_title` and `right_text`.

The test intentionally fails on regression cases when the matcher’s link decision disagrees with the expected grouping. Passing all 20 examples only shows agreement on these 20 cases, not generalization.

To establish representative event-link accuracy, independently annotate a legally usable, time-stamped collection of article pairs and report split, sample size, disagreement resolution, precision, recall and error categories.
