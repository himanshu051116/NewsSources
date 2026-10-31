# News Intelligence v1.25 — UI clarity & design refinement

This is a presentation-layer refinement on the operationally hardened v1.25 package. It is **not** a new intelligence methodology, schema migration, ingestion release, or claim that live production acceptance has passed. The application/package version stays `1.25.0`; Alembic remains `0033_grounded_news_explainer`.

## Critical findings

1. **Generic/technical positioning overtook human goals.** Many page leads discussed engine concepts (`ranked corpus retrieval`, `atomic claims`, `canonical entity registry`, `fidelity`, `grounded intelligence`) instead of explaining the user's next action. The headline and navigation should describe the job: find reports, follow events, compare versions, inspect sources.
2. **High-permission roles faced navigation overload.** The horizontal navigation exposed nine or more unrelated destinations with weak grouping. A permission-derived left rail now groups *Follow the story*, *Investigate*, *Review quality*, and *Administration*. A responsive drawer exposes the same complete set; owner/admin routes are never truncated.
3. **Generic cards were visually indistinguishable.** The original shell gave metrics, evidence, news and navigation essentially the same density and elevation. The updated system gives headline-driven pages distinct typography, muted metadata, compact metrics, clear section headings and restrained borders. Status color is reserved for meaningful states.
4. **Readers saw implementation details instead of sources.** The Event Briefing previously showed long opaque evidence IDs as pills, sometimes as many as six per sentence. It now shows numbered linked references, a source index with human-readable titles, original URLs, and a collapsed internal record ID. Unknown references are explicitly flagged rather than silently invented.
5. **Some UI counts implied broader scope than reality.** Home counts are derived from a latest-40-event/latest-100-report window. New labels and a visible scope explanation prevent them being mistaken for whole-corpus numbers. The News text-filter is explicitly described as filtering already loaded items, with a link to full-archive search. Event publisher counts are labeled as *publisher appearances*, not unique publisher confirmations.
6. **Sensitive admin actions used native browser prompts.** Access changes and publisher disablement now use explicit dialogs; suspension and revocation require a written reason. These changes preserve existing backend authorization and endpoints.
7. **A latent render-breaking defect existed in Article Evolution.** A destructuring expression inside a Python f-string was not escaped. Rendering the route could raise `NameError: name 'correction' is not defined`. It has been fixed and covered by regression testing.

## Copy examples (before → after)

| Prior wording | Updated user-facing wording | Why |
|---|---|---|
| `Ranked corpus retrieval` | `Search the archive` | Explains the task, not the ranking engine |
| `Search intelligence` | `Find a story or event` | Clearer action |
| `Continuous intelligence feed` | `Latest reporting` | Clear page purpose |
| `Article intelligence` | `Report details` | Easier for non-technical readers |
| `Publisher fidelity: Strong` | `Text capture: Good` | Avoids implying the publisher is credible/truthful |
| `Evidence map` (cards) | `Linked evidence` | Does not suggest a graph where there is no map |
| `Strongest historical links` | `Related earlier coverage` | Avoids ranking being mistaken for proof |
| `Entity Intelligence` | `People & organisations` | Human-readable navigation |
| `Entity Resolution Queue` | `Review matching names` | Conveys the reviewer action |
| `Observed lineages` | `Distinct source chains` | Helps readers understand duplicate reporting |
| Opaque evidence IDs on every briefing claim | `[1]`, `[2]` linked to source cards | Actual citation affordance |
| `PostgreSQL full-text` in the reader lead | `Find an event, report, claim or organisation` | Technical implementation remains in Search Quality and code |

`News Intelligence` stays as the product name. Technical terms (FTS, NDCG, p95, semantic reranking, lease fencing) remain on quality/operations surfaces where they carry precise meaning. No backend verification label, threshold, or confidence semantics were changed.

## Shared design and usability

- A consistent slate-blue/navy palette with lighter editorial reading surfaces and restrained semantic colors.
- Permission-aware desktop navigation; mobile drawer with labeled open/close controls, Escape handling, inert closed state and backdrop dismissal.
- Visible appearance switch (system-aware initial light/dark; user preference saved locally when browser storage allows).
- More legible reading scale, cards, metrics, tables, status pills, sections and focus states.
- A site-wide *How to read evidence and status labels* disclosure, distinguishing support from absolute truth, coverage from verification, and publisher diversity from independent reporting.
- Briefing layout with **What happened**, **Latest reporting**, **What changed**, **Why it matters**, **Historical context**, **Evidence supports**, **Disputed reports**, **Still unresolved**, **Corrections**, and **Sources and references**.
- Proper accessible dialogs for sensitive source and account operations rather than `prompt()` or `confirm()`.

## Verification performed

- **398 unit tests passed**, including six added focused UI/wording/browser-render contract tests; tests ran with a temporary external `structlog` stand-in because the sandbox does not have that frozen dependency. No shim is included in this release.
- All **40 generated JavaScript script blocks** across 20 rendered routes passed `node --check`, including the previously broken Article Evolution page.
- Chromium/Playwright local synthetic-data QA: desktop Home, mobile Home, desktop Event Briefing; menu open/Escape close, light/dark toggle, numbered-reference anchor navigation, and no horizontal overflow at 390px passed.
- Additional Chromium QA confirmed Access approval and Publisher disable dialogs can open and close without JavaScript page errors. Cookies/CSRF were locally stubbed only for that isolated browser demonstration (the application logic was unchanged).
- These checks are **not** a real database, authenticated OIDC, Docker deployment, accessibility audit by assistive technology, or live-source acceptance run. Those remain subject to the existing production runbook.

## Not changed

- SQL models/migrations, ranking, evidence/claim/lineage policies, external crawling, queues/workers, search deployment controls, report/briefing evidence pack generation, and production Compose topology.
- App version `1.25.0`. The ZIP name contains `ui-refined` to distinguish it from the earlier frozen package; the original v1.25 deployment gates remain required.

## Remaining UI work after real-user testing

- Replace server-generated inline JavaScript with modular assets if the UI is expanded further; that will also make a stronger Content Security Policy possible.
- Do a formal WCAG audit (screen readers, tab traps across every dialog, color-contrast automation and zoom testing) with the complete production app.
- Evaluate actual analyst tasks with representative users, especially evidence tracing, history interpretation and source operations. Screenshots and synthetic fixtures cannot prove usability across real data distributions.
- Avoid showing “confidence” as factual probability unless the specific measure is calibrated and explained.
