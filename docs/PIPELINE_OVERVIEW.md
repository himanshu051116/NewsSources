# Collection and processing pipeline

This diagram describes the **merged code path at a functional level**, not a claim that every publisher is currently reachable or that an operational news archive has been populated. It is based on the repository's source registry, collection workers, HTML/PDF extraction, PostgreSQL models, event/claim workflows and FastAPI reader.

## End-to-end flow

```mermaid
flowchart TB
    subgraph Acquisition["Source collection"]
        SRC["Publisher feeds, sitemaps and permitted URLs"]
        REG["Source registry and access policy"]
        JOB["Scheduled channels and URL frontier"]
        FETCH["Rate-limited, policy-aware HTTP fetch"]
        SRC --> REG --> JOB --> FETCH
    end
    subgraph Extraction["Article extraction"]
        TYPE{"Response content type"}
        HTML["HTML article text, canonical URL and timestamps"]
        PDF["Bounded PDF page text; OCR when enabled"]
        GATE{"Text usable?"}
        NORM["Normalize; retain article revisions and warnings"]
        FETCH --> TYPE
        TYPE -->|HTML| HTML --> GATE
        TYPE -->|PDF| PDF --> GATE
        GATE -->|yes or explicitly partial| NORM
    end
    subgraph Records["Storage and research"]
        PG[("PostgreSQL: sources, article versions, events, evidence")]
        EVENT["Event matching and shared-source lineage"]
        HISTORY["Historical search and claim review"]
        NORM --> PG
        PG --> EVENT --> HISTORY
    end
    subgraph Serving["Analyst access"]
        API["FastAPI: source records and retrieval"]
        UI["Local news reader and workspace"]
        PG --> API
        HISTORY --> API
        API <--> UI
    end
    WARN["Errors, warnings, retry state"]
    RAW["Permitted raw artifacts: local or S3-compatible storage"]
    FETCH -.->|fetch failure| WARN
    GATE -->|unusable| WARN
    GATE -.->|partial extraction warnings| WARN
    WARN -.->|retry if eligible| JOB
    FETCH -.->|when configured and permitted| RAW
```

## Operational boundaries

- **Discovery is not capture.** Feeds and sitemaps supply candidate URLs; policy, fetching and extraction determine whether a readable article enters the database. Source rights and retention decisions remain operator responsibilities.
- **HTML and PDF have different extraction paths.** PDF processing preserves page information and can optionally attempt OCR. An OCR result, table candidate or source-page link does not verify what a document asserts.
- **Normalization is not fact checking.** Duplicate detection, version history and canonical URLs describe content identity and change. The system can preserve several reports that share one underlying source.
- **PostgreSQL is the structured system of record.** Raw document artifacts may live in configured local/S3-compatible storage. Optional retrieval/vector services are omitted from this overview because they are not required for every local configuration.
- **Failures do not enter the successful path silently.** Fetch/retry outcomes and incomplete extractions are tracked. Retries follow eligibility and limits rather than looping indefinitely.
- **Research and serving are distinct.** Event identity, historical retrieval and claim review use stored records. The API serves those records to the reader; it does not turn a cited passage into an independently confirmed claim.

For more detail, see [acquisition policy](ACQUISITION_ARCHITECTURE.md), [event and evidence design](EVENT_INTELLIGENCE_ARCHITECTURE.md), [source data and evaluation](DATA_AND_EVALUATION.md), and the [production runbook](../PRODUCTION-RUNBOOK.md).

## Diagram scope

The README provides a short source-to-reader overview. This page expands the extraction branches, article-version persistence and recovery paths. It is a map of components and data movement, not a guarantee about collection success, publisher permissions or downstream factual correctness.
