# NewsSources Pages showcase

This folder is a **separate, static portfolio presentation** for the NewsSources project. It does not replace the FastAPI reader, run crawlers, use a database, or connect to publisher APIs.

## What visitors can do

- Inspect the project's collection, versioning, source-lineage and analysis workflow.
- Use a fictional research workbench: search four invented source records, filter revisions, compare passages, and switch between article review, lineage, timeline and claim audit views.
- Inspect an editorial claim register to distinguish unchanged figures, superseded figures and shared source origins, then jump to the relevant captures.
- Follow links back to the actual source repository and the implemented-architecture guide.

**Every demo article, publisher, date and quoted figure is invented.** The fake records deliberately share one evidence source to explain why multiple headlines are not automatically independent confirmation. No personal data or production credentials are used or transmitted. There are no third-party scripts, web fonts, tracking tags or remote API calls.

## Local preview

From the repository root:

~~~sh
python -m http.server 8088 --directory showcase
~~~

Visit http://127.0.0.1:8088/ and inspect both mobile and desktop layouts. All CSS, JavaScript and the favicon are relative assets, so they also work under the GitHub Pages project path /NewsSources/.

Offline file checks and a JavaScript syntax check:

~~~sh
python .github/scripts/validate_showcase.py
node --check showcase/app.js
~~~

The site remains useful without JavaScript, but its fictional workbench needs JavaScript for interaction.

### Browser regression tests

Playwright tests run against a local Python static server. From the repository root (Node.js 22+ and Python 3 required):

~~~sh
cd showcase/tests
npm install
npx playwright install chromium
npm test
~~~

The test configuration starts and stops the local server automatically. It tests desktop Chromium and a narrow/mobile Chromium viewport, including boot errors, search/filter/reset, claim audit, source relationships, timeline selection and stepping, passage drilldowns, revision highlighting, keyboard navigation and the absence of remote requests.

The GitHub Pages workflow runs the same test suite on pull requests and main; deployment to Pages now depends on successful validation **and** browser smoke tests. The tests are development dependencies only and are not included in the published `showcase/` artifact because the Pages upload step must exclude the `tests/` directory.

## Pages deployment — active on main

The workflow is [pages-showcase.yml](../.github/workflows/pages-showcase.yml).

1. Open the deployed [NewsSources showcase](https://himanshu051116.github.io/NewsSources/). This is a static portfolio view, not the live FastAPI platform.
2. The Pages workflow is enabled on **main**. An approved pull request that changes the showcase triggers validation; publishing runs only after the change is merged into **main**.
3. Confirm the deployment in [GitHub Actions](https://github.com/himanshu051116/NewsSources/actions/workflows/pages-showcase.yml).
4. Changes to a feature branch never overwrite the live website before review.

The workflow prepares a static deployment of the site. The site does not call the backend, crawlers, databases, live publisher feeds or private services. Browser-test sources live under `showcase/tests/` and are not website features.

### Exhibit v0.5
- Four **invented** records (one original notice, two derived reports, one revision)
- A case briefing strip with visible original/derived/revision indicators
- A fourth workbench tab: claim audit, with three labeled synthetic claims, editorial follow-up questions and source jumps
- A guided three-step case tour and dedicated derived-report filter
- A structured lineage explorer with four selectable source nodes and an evidence inspector
- Explicit links from one notice to two derived reports and a later same-issuer revision
- Dedicated source-inspector action to open the selected passage (or compare the revision)
- An interactive four-capture chronology with a selection rail, event inspector, source lineage, editorial notes, and earlier/later navigation
- Explicit **Inspect passage** / **Compare correction** actions that open the existing article review without duplicating its evidence
- Safe side-by-side comparison with the fictional 240 → 215 revision highlighted
- A visible explanation of what source provenance can and cannot prove
- Keyboard-operated tabs, responsive layouts, local assets and a restrictive site CSP

Browser QA runs in CI on desktop and mobile Chromium. The offline validator checks the structural invariants, including multi-element selectors; only the browser suite exercises real DOM events. Inspect failing traces rather than approving a pull request on syntax checks alone.

Suggested smoke test:
1. Choose **Claim audit** and switch through all three claim cards; the evidence values and editorial question must update.
2. Use **Compare revision** from CLM-02; Article review should open SRC-004 with 240 and 215 highlighted.
3. Filter records to **Derived**, then use the guided source tour and **Reset demo**; neither should throw JavaScript errors.
4. In **Timeline**, click each of the four fictional captures, use Earlier/Later, and open the final correction to verify the side-by-side 240 → 215 comparison.
5. Use arrow keys/Home/End between tabs, then press Enter on a timeline capture and check all four views at mobile width.
6. Confirm that opening the site makes no network calls to publisher or backend APIs.


## Maintenance

- index.html: editorial copy and semantic layout
- styles.css: responsive visual system and reduced-motion styles
- app.js: fully local fictional records, claim audit, lineage and timeline inspectors, and guided interactions
- tests/: browser regression suite and Playwright configuration (not part of the public-facing UI)
- favicon.svg: local vector brand mark
- .github/scripts/validate_showcase.py: basic link, privacy and structure checks

When documenting a new runtime feature, verify it against the implementation rather than proposed design documents. Do not use live publisher text or screenshots without permission. See the repository [implemented architecture](../docs/IMPLEMENTED_ARCHITECTURE.md) and [project status](../docs/STATUS.md).

## Rights

The application declares a proprietary license in pyproject.toml; publishing this static showcase does not change the repository's licensing or grant third-party reuse rights.

## Upgrade branch sequence

Pages v0.5 builds upon the v0.4 lineage and browser-test work. The new timeline reuses the four synthetic source records and requires no backend, publisher permissions, secrets or browser storage. Review the underlying v0.4 changes before considering the dependent v0.5 work for deployment.
