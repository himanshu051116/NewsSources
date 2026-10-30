from newsintel.adapters.collectors.sitemaps import (
    SitemapDocumentType,
    parse_sitemap,
)


def test_parses_google_news_sitemap_fields() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url>
        <loc>https://example.com/news/one</loc>
        <lastmod>2026-06-25T10:01:00Z</lastmod>
        <news:news>
          <news:publication_date>2026-06-25T10:00:00Z</news:publication_date>
          <news:title>One</news:title>
        </news:news>
      </url>
    </urlset>"""

    document = parse_sitemap(xml)

    assert document.document_type is SitemapDocumentType.URL_SET
    assert document.entries[0].publication_date_raw == "2026-06-25T10:00:00Z"
    assert document.entries[0].news_title == "One"


def test_parses_sitemap_index() -> None:
    xml = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/news-1.xml</loc></sitemap>
    </sitemapindex>"""

    document = parse_sitemap(xml)

    assert document.document_type is SitemapDocumentType.INDEX
    assert document.entries[0].location == "https://example.com/news-1.xml"



def test_marks_google_news_sitemap_and_publication_metadata() -> None:
    xml = """<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"
        xmlns:news=\"http://www.google.com/schemas/sitemap-news/0.9\">
      <url><loc>https://example.com/news/one</loc><news:news>
        <news:publication>
          <news:name>Example News</news:name><news:language>en</news:language>
        </news:publication>
        <news:publication_date>2026-08-13T00:00:00Z</news:publication_date>
        <news:title>One</news:title>
      </news:news></url>
    </urlset>"""

    document = parse_sitemap(xml)

    assert document.contains_news is True
    assert document.entries[0].is_news is True
    assert document.entries[0].news_publication_name == "Example News"
    assert document.entries[0].news_language == "en"


def test_parses_gzipped_sitemap() -> None:
    import gzip

    xml = b"""<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
      <url><loc>https://example.com/news/story-one-today</loc></url>
    </urlset>"""

    document = parse_sitemap(gzip.compress(xml))

    assert document.compressed is True
    assert document.entries[0].location.endswith("story-one-today")
