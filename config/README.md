# Source pack: operator notes

`live-source-pack.json` contains **candidate publisher endpoints**, not a curated live feed dataset.

The set covers English/Hindi Press Information Bureau releases, two Guardian sections and a SEBI announcements listing. It is useful for checking different acquisition paths, **not** a claim that all endpoints work today or that the project has redistribution rights.

`newsintel-seed-sources` reads `name`, `website_url`, `fetch_frequency` and `manual_endpoints`. The extra `review` metadata records uncertainty but **is not an enforcement gate**. The operator must check each URL, source terms, robots directives and retention before running the seeder.

Notes:
- The SEBI entry points to an HTML announcement listing, **not an RSS feed**; successful discovery depends on the adapter and page structure.
- The two PIB entries use different proposed language feed URLs; current feed availability and parameters have not been re-tested by this repository presentation pass.
- The two Guardian sources share a publisher; different sections are **not independent ownership lineages**.
- `fetch_frequency` is an *intended polling cadence*, not a guaranteed publication-to-discovery time.

Use `docs/DATA_AND_EVALUATION.md` to record editorial provenance before claiming real-world coverage.

## Record-level review fields

Each source has a `review_metadata` object, with a stable source key, publisher group, expected language, the expected endpoint type and explicit null review timestamps. These are **operator annotations**, not live tests or authorization controls. `publisher_group` lets analysts see that Guardian World and Guardian Technology share a publisher; it does not independently prove ownership or syndication on specific articles.

The SEBI listing is marked `html_listing_candidate` rather than claiming it exposes a working RSS channel. All `retention_approved` values default to `false`. This field is *not currently enforced by the source seeder*; operators must review rights before use.

Never replace the null timestamps with guessed dates. Only record an actual manual check, its reviewer and the observed result.
