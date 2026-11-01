# NewsSources Pages showcase

This folder is a **separate, static portfolio presentation** for the NewsSources project. It does not replace the FastAPI reader, run crawlers, use a database, or connect to publisher APIs.

## What visitors can do

- Inspect the project's collection, versioning, source-lineage and analysis workflow.
- Use a fictional research workbench: search four invented source records, filter revisions, compare passages, switch between article review, lineage and timeline views.
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

## Pages deployment — active on main

The workflow is [pages-showcase.yml](../.github/workflows/pages-showcase.yml).

1. Open the deployed [NewsSources showcase](https://himanshu051116.github.io/NewsSources/). This is a static portfolio view, not the live FastAPI platform.
2. The Pages workflow is enabled on **main**. An approved pull request that changes the showcase triggers validation; publishing runs only after the change is merged into **main**.
3. Confirm the deployment in [GitHub Actions](https://github.com/himanshu051116/NewsSources/actions/workflows/pages-showcase.yml).
4. Changes to a feature branch never overwrite the live website before review.

The workflow publishes only the `showcase/` directory; there is no backend, crawler, database, live publisher feed or secret in the Pages artifact.

### Exhibit v0.2
- Four **invented** records (one original notice, two derived reports, one revision)
- A guided three-step case tour and dedicated derived-report filter
- Selectable source-lineage nodes and clickable timeline entries
- Safe side-by-side comparison with the fictional 240 → 215 revision highlighted
- A visible explanation of what source provenance can and cannot prove
- Keyboard-operated tabs, responsive layouts, local assets and a restrictive site CSP

Browser QA should cover keyboard navigation, mobile widths, filtering, source selection, the revision comparison and the reset control.


## Maintenance

- index.html: editorial copy and semantic layout
- styles.css: responsive visual system and reduced-motion styles
- app.js: fully local fictional records, guided tour and interactions
- favicon.svg: local vector brand mark
- .github/scripts/validate_showcase.py: basic link, privacy and structure checks

When documenting a new runtime feature, verify it against the implementation rather than proposed design documents. Do not use live publisher text or screenshots without permission. See the repository [implemented architecture](../docs/IMPLEMENTED_ARCHITECTURE.md) and [project status](../docs/STATUS.md).

## Rights

The application declares a proprietary license in pyproject.toml; publishing this static showcase does not change the repository's licensing or grant third-party reuse rights.
