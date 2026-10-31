# News Intelligence 1.23.0 — Live Pipeline Hardening

## Goal
Return development to the original product mission: truthful, continuous article acquisition before adding more intelligence surface area.

## Implemented
- fenced poller and article-processing leases with monotonically increasing lease versions and heartbeats;
- exact manual fetch-job lineage across channel polls, discoveries, candidates and article fetch runs;
- `fetch_job_observations` so manual job counts no longer include unrelated scheduled polling;
- conservative cross-URL article identity/syndication foundation using stored content fingerprints and high similarity thresholds;
- live-source starter pack plus seeding CLI;
- additional runtime health signals for recent ingestion/history and stale leases.

## Guardrails
- source identity similarity reduces duplicate/independence risk; it is never treated as factual verification;
- starter sources remain subject to publisher terms/licensing/retention review;
- heartbeat/fencing protects commits after lease takeover.
