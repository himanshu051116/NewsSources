# News Intelligence 1.24.0 — Grounded News & Historical Explainer

## Goal
Turn the platform's event/claim/evidence/history records into the user-facing product promise: explain what happened, what changed, what came before and what remains uncertain.

## Implemented
- event briefing persistence and fenced briefing jobs;
- automatic queueing after historical enrichment plus backfill for older contexts;
- automatic refresh when current event state, verification decisions, history or corrections become newer than the briefing;
- deterministic evidence-pack construction from current article versions, claims, verification states, corrections and historical matches;
- per-statement evidence IDs and a stable evidence-pack SHA-256;
- explicit sections for established facts, disputed/contradicted claims, unresolved claims, historical context and analytical "why it matters";
- API and authenticated Event Briefing UI.

## Epistemic guardrail
The explainer uses stored platform records only. It does not fill missing context from model/world knowledge. Unresolved evidence remains unresolved.
