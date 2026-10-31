# Implemented architecture

**Checked against the repository on 31 October 2026.** This is a code map for the application on `main`. It is not a deployment report or a statement that every optional integration is enabled. The package metadata still reports version `1.25.0` despite subsequent merged changes.

## Runtime map

| Responsibility | Checked-in implementation |
| --- | --- |
| Feed and sitemap discovery | [Feeds](../backend/src/newsintel/adapters/collectors/feeds.py), [sitemaps](../backend/src/newsintel/adapters/collectors/sitemaps.py), [poller](../backend/src/newsintel/workers/poller.py) |
| Policy-aware fetching | [Safe fetcher](../backend/src/newsintel/adapters/http/safe_fetcher.py) and [robots/rate policies](../backend/src/newsintel/adapters/http/crawl_policy.py) |
| Article worker and extraction | [Article worker](../backend/src/newsintel/workers/articles.py), [HTML extractor](../backend/src/newsintel/adapters/extractors/article_html.py), [PDF extractor](../backend/src/newsintel/adapters/extractors/document_pdf.py) |
| Article processing and versioning | [Processing service](../backend/src/newsintel/application/articles/processing.py), [database models](../backend/src/newsintel/infrastructure/db/models.py), [revision-history migration](../backend/migrations/versions/0034_article_revision_history.py) |
| Event and evidence handling | [Event matching](../backend/src/newsintel/domain/events/matching.py) and domain modules under `backend/src/newsintel/domain/intelligence/` |
| Background workers | [Polling](../backend/src/newsintel/workers/poller.py), [articles](../backend/src/newsintel/workers/articles.py), [historical enrichment](../backend/src/newsintel/workers/historical_enrichment.py), [briefings](../backend/src/newsintel/workers/briefings.py) |
| Source and reader interfaces | [Source routes](../backend/src/newsintel/api/routes/sources.py), [news reader](../backend/src/newsintel/api/routes/news_dashboard.py), [historical reader](../backend/src/newsintel/api/routes/historical_dashboard.py) |
| Optional raw artifact backends | [Local artifact store](../backend/src/newsintel/adapters/artifacts/local_store.py), [S3-compatible artifact store](../backend/src/newsintel/adapters/artifacts/s3_store.py) |

## Dependencies and boundaries

- **Required local services:** Python application and PostgreSQL; the Windows start script provisions the default database container and starts the API plus workers.
- **Not part of the default local stack:** Qdrant semantic history, MinIO/S3-compatible object storage, and an isolated browser renderer. They require separate configuration or enablement; local raw-artifact storage is supported.
- **Rendering:** the checked-in reader pages are served by FastAPI routes and Python-side page templates. Do not describe the working UI as a deployed Next.js frontend.
- **PDFs:** extraction is bounded and page-aware. Optional Tesseract OCR (`eng+hin` by default when enabled) can be used for scanned pages. PDF-related signals and table candidates require human review.
- **Security and operations:** production access controls, publication rights, backup/restore drills and live publisher acceptance remain deployment responsibilities. A green CI run does not certify these.

## Which architecture document to read

Use the [collection and processing pipeline](PIPELINE_OVERVIEW.md) for a compact data-flow diagram and this page for the checked-in modules. The original [June 2026 system-architecture proposal](ARCHITECTURE.md) also mentions Kafka/Redis infrastructure, a Next.js dashboard, and model services. Those are design possibilities, **not a list of default or verified running services**.

Local setup: [Windows guide](../SETUP-WINDOWS.md). Current merged changes and remaining validation: [project status](STATUS.md).
