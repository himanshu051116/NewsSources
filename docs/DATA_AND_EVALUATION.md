# Data provenance and evaluation

This repository combines **publisher configuration**, **locally captured reporting**, and **constructed test fixtures**. They serve different purposes and must never be combined into one “accuracy” figure.

## Source configuration

`config/live-source-pack.json` lists candidate endpoints for English/Hindi government releases, a commercial publisher and regulatory announcements. The entries are *operational starting points*, not a license or promise that each feed currently responds correctly. The source-seeding script reads the existing `sources` fields and attempts discovery through the crawl-policy fetcher; the metadata fields are descriptive and do not bypass any checks.

Before enabling a source, record:
- Date and HTTP/format outcome of a manual endpoint check;
- Publisher’s current robots directives, terms and permissible retention;
- Language and expected article/PDF formats;
- Review owner, source scope and any reproduction limits;
- Observed freshness and extraction failure rate after a pilot.

No such live evidence is bundled or asserted in this documentation.

## Event grouping regression fixture

`backend/tests/fixtures/accuracy/event_pairs.json` contains **20 constructed examples**: 10 intended same-event and 10 intended different-event pairings. Examples exercise Hindi/English lexical overlap, numbers, shared organizations, similar geography and hard negatives. Labels encode the test author’s intended grouping for these invented/reconstructed examples; they are **not independently adjudicated real-world event IDs**.

Run `python qa/validate_repository_data.py` for schema and provenance checks, then the event-accuracy unit test to see whether current matching behavior agrees with the intended labels.

## Inspectable fictional scenario

[The correction-and-source-lineage walkthrough](../examples/README.md) uses a deliberately invented municipal bulletin, two derivative articles, a later correction and a different nearby incident. It is an editorial design example, **not crawled reporting**, benchmark evidence or an importable database fixture.

## Real-world evaluation still required

For defensible editorial claims, assemble a permissioned corpus with archived source URLs, capture times, publisher revision snapshots, rights/retention notes, annotator instructions, independent double review and disagreement adjudication. Split by event and source lineage to avoid train/test leakage. Report **event linking**, **extraction fidelity**, **citation location**, **factual adjudication** and **abstention** separately.

PDF/OCR benchmarks belong to the draft PDF branch. Synthetic page fixtures validate code paths; they cannot substitute for varied scans, complex layouts, Hindi glyph quality, table transcription and verified citation labels.

Never present locally reconstructed QA HTML, screenshots or synthetic fixtures as verbatim source documents.
