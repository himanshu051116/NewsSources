from newsintel.adapters.extractors.article_html import extract_article_html
from newsintel.domain.intelligence.extraction_fidelity import assess_extraction_fidelity


def test_fidelity_report_is_strong_when_extraction_preserves_publisher_signals() -> None:
    body = (
        "A cargo vessel carrying 1,700 tonnes of iron ore sank 240 nautical miles "
        "off the Odisha coast. The ship had 24 crew members aboard. "
    ) * 5
    html = f'''<html><head>
      <title>Cargo vessel sinks off Odisha coast</title>
      <meta property="og:title" content="Cargo vessel sinks off Odisha coast" />
      <meta property="og:url" content="https://example.com/india/cargo-vessel-sinks" />
      <meta property="article:published_time" content="2026-08-22T22:11:00+05:30" />
      <link rel="canonical" href="https://example.com/india/cargo-vessel-sinks" />
      <script type="application/ld+json">{{
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "url": "https://example.com/india/cargo-vessel-sinks",
        "headline": "Cargo vessel sinks off Odisha coast",
        "datePublished": "2026-08-22T22:11:00+05:30",
        "articleBody": {body!r}
      }}</script>
    </head><body><article><p>{body}</p></article></body></html>'''.replace("'", '"').encode()

    article = extract_article_html(html, base_url="https://example.com/india/cargo-vessel-sinks")
    report = assess_extraction_fidelity(
        html,
        base_url="https://example.com/india/cargo-vessel-sinks",
        article=article,
    )

    assert report.label == "strong"
    assert report.score is not None and report.score >= 0.9
    assert report.checks["title_consistency"] == 1.0
    assert report.checks["canonical_consistency"] == 1.0
    assert report.checks["publication_time_consistency"] == 1.0
    assert report.checks["structured_numeric_retention"] == 1.0


def test_fidelity_report_flags_material_metadata_and_body_mismatch() -> None:
    structured_body = (
        "The official bulletin recorded 24 crew members and a distance of 240 nautical miles. "
    ) * 6
    html = f'''<html><head>
      <meta property="og:title" content="Official cargo vessel update" />
      <meta property="article:published_time" content="2026-08-22T20:00:00Z" />
      <link rel="canonical" href="https://example.com/official-story" />
      <script type="application/ld+json">{{
        "@type": "NewsArticle",
        "headline": "Official cargo vessel update",
        "datePublished": "2026-08-22T20:00:00Z",
        "articleBody": {structured_body!r}
      }}</script>
    </head><body><p>A completely different short teaser with no useful figures.</p></body></html>'''.replace("'", '"').encode()

    article = extract_article_html(html, base_url="https://example.com/official-story")
    # Simulate a materially incorrect downstream extraction while retaining the
    # immutable ExtractedArticle structure used by the real pipeline.
    article = type(article)(
        title="Different headline",
        byline=article.byline,
        published_at=article.published_at,
        modified_at=article.modified_at,
        language=article.language,
        canonical_url="https://example.com/wrong-story",
        text_content="A completely different short teaser with no useful figures.",
        content_sha256=article.content_sha256,
        extraction_method=article.extraction_method,
        metadata=article.metadata,
        warnings=article.warnings,
    )
    report = assess_extraction_fidelity(
        html,
        base_url="https://example.com/official-story",
        article=article,
    )

    assert report.label == "weak"
    assert "headline_differs_from_publisher_metadata" in report.discrepancies
    assert "canonical_url_differs_from_publisher_metadata" in report.discrepancies
    assert "extracted_body_has_low_structured_body_coverage" in report.discrepancies
    assert "one_or_more_structured_numeric_facts_missing" in report.discrepancies
