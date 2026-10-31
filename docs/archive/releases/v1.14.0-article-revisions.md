# News Intelligence 1.14.0 — Article Evolution & Correction Intelligence

## What changed

This release adds an analyst-facing article-evolution workspace at `/articles/{article_id}/evolution` and connects existing versioning/correction infrastructure to the UI.

### Version evolution
- Stored article versions are shown as immutable snapshots.
- Adjacent versions expose deterministic structured diffs.
- Added/removed/replaced/material/numeric/temporal changes are surfaced separately.
- Old/new text is shown side by side.
- Extraction warnings and content hashes remain visible for provenance.

### Correction review
- Deterministic correction candidates are displayed as review signals only.
- Candidate confidence is explicitly labelled detection confidence, not truth confidence.
- Human verifier permission is required to register a correction/retraction/update/clarification.
- Already-registered version/kind candidates are suppressed in the UI.
- Registration uses an explicit modal and preserves historical verification decisions.

### Affected-claim precision
- Reviewers must select affected claims explicitly, or explicitly choose all claims in the target version.
- This prevents a blank affected-claim list from unintentionally flagging every claim in a version.

### Claim evolution
- Claim families are shown across article versions.
- Changed, stable, active-latest, and retired claim families are distinguishable.
- Each revision links into the dedicated Claim Investigation workflow.

### Downstream correction impact
- Registered correction events expose direct and indirect dependency-propagation runs.
- Impact severity, depth, rationale, and review actions are visible.
- Claim review flags can be opened in Claim Investigation and, with verifier permission, marked reviewed with an audit note.

## Guardrails preserved
- A material article change is not automatically a factual correction.
- Correction detection never creates a correction event automatically.
- Correction registration does not silently rewrite prior verification labels.
- Dependency propagation creates review obligations rather than automatic verdict reversals.

## Validation
- Python compilation: PASS
- Generated Article Evolution JavaScript syntax check with Node: PASS
- Selected regression suite: 74 tests PASS
- The sandbox still does not provide every frozen production dependency, so this does not claim a complete end-to-end production runtime validation.

## Recommended next phase
1. Investigation collections and analyst notes.
2. Saved searches and watchlists.
3. Alert rules for new material changes, corrections, conflicts, and watchlisted entities/events.
4. PostgreSQL full-text ranking/cursor pagination for global search.
5. Production integration tests against real PostgreSQL/PostGIS.
