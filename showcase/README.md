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

## Pages deployment — prepared, not yet published

The workflow is [pages-showcase.yml](../.github/workflows/pages-showcase.yml).

1. Review the **draft** pull request and the **Validate static showcase** check. Do not enable publishing from an unreviewed feature branch.
2. In **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**. GitHub requires repository administration access to configure Pages.
3. Review the github-pages environment. Restrict deployments to the protected main branch if environment branch rules are available.
4. Merge the approved PR into main. The workflow will validate assets, then publish **only this showcase/ directory** through GitHub Pages. No Python code, secrets or repository root files are included in the published artifact.
5. Check the Pages URL displayed in GitHub Settings or the workflow's deploy job. The expected project URL, after successful publication and unless a custom domain is configured, is https://himanshu051116.github.io/NewsSources/.

**Safety gate:** Pull requests only run validation. Deployment is conditional on refs/heads/main and is never triggered by pushes to the feature branch. GitHub Pages and deployment permissions must be configured before the first successful publication.

## Maintenance

- index.html: editorial copy and semantic layout
- styles.css: responsive visual system and reduced-motion styles
- app.js: fully local fictional records and interactions
- favicon.svg: local vector brand mark
- .github/scripts/validate_showcase.py: basic link, privacy and structure checks

When documenting a new runtime feature, verify it against the implementation rather than proposed design documents. Do not use live publisher text or screenshots without permission. See the repository [implemented architecture](../docs/IMPLEMENTED_ARCHITECTURE.md) and [project status](../docs/STATUS.md).

## Rights

The application declares a proprietary license in pyproject.toml; publishing this static showcase does not change the repository's licensing or grant third-party reuse rights.
