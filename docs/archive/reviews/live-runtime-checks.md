# News Intelligence v1.25 — Live-runtime attempt and critical UI/results QA

Date: 14 October 2026 (QA exercise); build: v1.25 UI-refined with corrective patch.

## Verdict

**Not yet certified as a functioning 24/7 live production installation.** Main FastAPI pages work in this environment and the actual extraction/claim extraction functions were executed. The full live publisher → poller → article DB → historical worker → briefing worker loop could not be started because the runtime has **no Docker daemon, no PostgreSQL instance, missing locked packages including asyncpg/structlog, and public DNS/HTTP access is blocked from this Python container**. Browser `page.goto` is also administratively blocked; tests therefore render the *actual FastAPI HTML* through an in-process TestClient and run its actual JavaScript in Chromium with explicitly replayed API responses. These are substantive functional tests **but not an end-to-end live ingestion test**.

## What was actually exercised

| Test | Evidence | Result |
|---|---|---|
| Actual FastAPI page handlers | QA app using `create_app()` with database lifespan/auth replaced only for read-only QA | HTTP 200 on Home, News, Briefing; generated scripts checked |
| Desktop and mobile interactions | Chromium rendered actual server HTML with source replay JSON | 28/28 functional assertions, zero JS page errors, zero console errors |
| Mobile layout | 390px viewport | No horizontal overflow, menu open and Escape close, functional filters |
| Desktop layout | 1440px viewport | Sidebar, metrics, news cards, theme toggle, historical source reference links |
| Main app scripts | Node `--check` on actual FastAPI-rendered inline scripts | 10/10 script blocks passed across 5 key routes |
| HTML extraction | Genuine `extract_article_html()` on short, locally reconstructed paragraphs from 2 verified official releases | 2 documents extracted, canonical URL/published time retained; `low_extraction_quality` warning as expected for artificially short text |
| Claim candidates | Genuine deterministic `extract_claims()` | 8 candidate propositions extracted, **zero independent verification decisions** |
| Unit regression | Frozen v1.25 source plus fixes | **404/404 passed** with external test-only `structlog` shim (not packaged as a runtime dependency) |
| Python compilation | `compileall` on sources, tests, migrations, QA files | Pass |
| Dependency lock | `uv lock --check --offline` | Pass |
| Full real database / worker / production UI | Requires Docker/Postgres/asyncpg/live egress | **BLOCKED — NOT TESTED** |
| Seven-day acceptance | Requires continuously operating real sources and services | **NOT PERFORMED** |

### Source-based result sample — reproduced, not fetched by the app

1. **13 Oct 2026, PIB / Ministry of Coal:** MCL e-waste-cleanup drive, reported 73 of 240 sites cleaned, 306,663 square feet and 350 batteries. `https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2322767`
2. **13 Oct 2026, PIB / Ministry of Commerce & Industry:** PM GatiShakti five-year update, government states more than 1,800 data layers, 58 central departments, 36 states/UTs, over 400 projects worth ₹20.23 lakh crore. `https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2322825`
3. **13 Oct 2021, original PM GatiShakti launch:** `https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1763576&lang=2&reg=48`
4. **5 Aug 2025, PIB progress report:** 293 reviewed projects worth ₹13.59 lakh crore, explicitly from a government written reply. `https://www.pib.gov.in/PressReleasePage.aspx?PRID=2152521&lang=2&reg=3`
5. **13 Oct 2026, SEBI listing:** A consultation-paper listing was included in QA dashboard; the article body was **not** fetched. Official listing: `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&sid=6&smid=0&ssid=0`

Source bodies were **manually paraphrased and reconstructed into short local HTML** based on public official documents accessed separately through web retrieval. The app did **not** fetch these pages through its source crawler; the dashboard replay responses were **not** persisted by the application; the pictured briefing is **manually assembled source-replay data**, not a result from the application briefing worker. The QA UI is visibly watermarked to make this distinction unavoidable.

## Bugs found and changed in production code

1. **Feed corruption when loading older stories.** Offset pages could drift when background refresh prepended new articles. Implemented stable keyset seeking by `(first_observed_at, id)` in article query service, API cursor parameters with validation, and stateful News pagination independent of refresh.
2. **Nonfunctional or misleading controls.** The News “Load older stories” button remained visible when no older page existed because global `button {display:...}` overrode user-agent `[hidden]`. Explicit global `[hidden]{display:none!important}` and tested behavior.
3. **Duplicate/noisy story metadata.** The listing repeated date/status and displayed up to five status pills plus actions per story. Removed duplicate metadata and redundant badge rows; preserves detailed extraction warnings in report detail views.
4. **Short-article extraction pollution.** Leading article H1 was duplicated verbatim as body text, creating a spurious headline-first candidate claim. Remove the redundant title block if the first extracted text equals the title.
5. **False paywall heuristic.** Generic footer `Subscribe now` by itself triggered a paywall/partial-content warning. Do not infer paywall from a generic subscription footer alone.
6. **Briefing titles mismatch.** Briefing serializer emitted `latest_reporting[].text` but UI read `.title`, producing “Untitled report.” Fixed the serializer; UI also accepts earlier serialized `.text` records.
7. **Briefing evidence trace.** “Supported” claim output previously cited only a claim record. Added stored evidence-link reference IDs/source cards; stored `SUPPORTED` claims with no traceable support are labeled as unresolved evidence-trace issues, not displayed as proof.
8. **Unsupported impact claims.** Removed the unsubstantiated generic assertion that the event *has* a defined impact; the section now describes missing impact evidence explicitly and uses more cautious copy.
9. **False operational-health cue.** Removed decorative green “live” status next to sidebar branding; it did not reflect actual ingestion health.
10. **Historical QA integrity.** Replaced a 2026 retrospective incorrectly dated 2021 with actual 2021 PIB launch and added an actual August 2025 historical source, preserving original dates and URLs.

## UI design review

- **Improved:** desktop information hierarchy and navigation; mobile compact cards; visible evidence/source references; no misleading “live” branding; clear partial-extraction labels; mobile filters and theme; source labels clickable.
- **Still needs live-user evaluation:** full article investigation workflow with real documents and long titles, screen reader/navigation audit, cross-browser verification, large corpus search/load testing, complex conflicting-claims briefings, first-use source onboarding, permission-specific views, and real operational status/incident views.
- **Safety of status labels:** "History ready" means enrichment data exists, not that historical facts are independently verified. "Supported" refers to the stored verification policy and traceable evidence, not a universal truth guarantee.

## Reproducing the checks in a prepared environment

With all locked dependencies installed, from the project root:

```bash
PYTHONPATH=backend/src pytest backend/tests/unit -q
uv lock --check --offline
PYTHONPATH=backend/src python qa/source_replay_pipeline.py
PYTHONPATH=backend/src python qa/verify_rendered_js.py
PYTHONPATH=backend/src python qa/browser_e2e.py
python scripts/release-integrity.py --json
```

`qa/` uses replay fixtures, bypasses the production database lifespan, and is **never** a substitute for the actual acceptance trial. QA browser tests additionally require Playwright/Chromium. In the test sandbox only, `PYTHONPATH=/tmp/newsintel_test_stubs` supplied a non-shipped `structlog` stand-in for test collection.

## Production acceptance gate — still required

On a properly provisioned Linux host with Docker, real PostgreSQL and all dependencies, and outbound publisher access:

1. Build/start all production services; run Alembic and verify health, migrations, secrets and permissions. Confirm a real `GET /api/v1/articles` response from the deployed DB.
2. Seed **approved** sources, log actual discovery/fetch timestamps and source licences, and verify raw HTML artifacts and source text against publisher pages.
3. Confirm actual article versions, event grouping, candidate claims, evidence provenance, historical matches and generated briefings on live documents with independent human review.
4. Run 24h, 72h and 7-day acceptance with real ingress, alerting, backups and a restore drill. Collect completion/failure rates, historical relevance, citation traceability, latency and failure cases.
5. Review reports for release GO/NO-GO. Until then, status is **source-code QA passed / production live acceptance not performed**.
