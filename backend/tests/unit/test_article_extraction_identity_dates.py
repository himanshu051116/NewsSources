"""Do not import an old/related story's content or date into the fetched article."""

import json
from datetime import UTC, datetime

import pytest

from newsintel.adapters.extractors.article_html import extract_article_html

CURRENT_URL = "https://news.example/news/flood-response"
CURRENT_TITLE = "Flood response expands across districts"
CURRENT_BODY = " ".join([
    "The state government published district figures and opened emergency shelters after flooding."
] * 8)
OLD_BODY = " ".join([
    "The tennis player described winning a tournament several years ago in an archive interview."
] * 25)


@pytest.fixture(autouse=True)
def deterministic_extractors(monkeypatch):
    monkeypatch.setattr(
        "newsintel.adapters.extractors.article_html._extract_with_trafilatura",
        lambda *args, **kwargs: None,
    )


def extract(payload=None, *, hydration=None, extra_meta="", page_title=CURRENT_TITLE):
    structured = (f'<script type="application/ld+json">{json.dumps(payload)}</script>'
                  if payload is not None else "")
    if hydration is not None:
        structured += (f'<script id="__NEXT_DATA__" type="application/json">'
                       f'{json.dumps(hydration)}</script>')
    html = (f'<html><head><link rel="canonical" href="{CURRENT_URL}">'
            f'<meta property="og:title" content="{page_title}">{extra_meta}{structured}'
            f'</head><body><article><p>{CURRENT_BODY}</p></article></body></html>')
    return extract_article_html(html.encode(), base_url=CURRENT_URL + "?utm_source=feed")


def current_record():
    return {"@type": "NewsArticle", "headline": CURRENT_TITLE,
            "mainEntityOfPage": {"@id": CURRENT_URL + "#article"},
            "datePublished": "2026-10-29T04:00:00Z", "articleBody": CURRENT_BODY}


def old_record():
    return {"@type": "NewsArticle", "headline": "Tennis champion remembers historic victory",
            "url": "https://news.example/sports/old-tennis-interview",
            "datePublished": "2021-01-01T04:00:00Z", "articleBody": OLD_BODY}


def test_json_ld_uses_current_url_instead_of_longest_related_story():
    article = extract({"@graph": [old_record(), current_record()]})
    assert article.title == CURRENT_TITLE
    assert article.published_at == datetime(2026, 10, 29, 4, tzinfo=UTC)
    assert article.text_content == CURRENT_BODY
    assert article.extraction_method == "json_ld_article_body"


def test_nested_main_entity_is_detected_and_matched_to_page():
    record = current_record()
    record["@type"] = "https://schema.org/NewsArticle"
    article = extract({"@type": "WebPage", "url": CURRENT_URL, "mainEntity": record,
                       "relatedLink": old_record()})
    assert article.title == CURRENT_TITLE
    assert article.published_at == datetime(2026, 10, 29, 4, tzinfo=UTC)
    assert article.text_content == CURRENT_BODY


def test_headline_identity_selects_article_when_structured_urls_are_absent():
    current, related = current_record(), old_record()
    del current["mainEntityOfPage"]
    del related["url"]
    article = extract([related, current], page_title=CURRENT_TITLE + " | News Example")
    assert article.text_content == CURRENT_BODY
    assert article.title == CURRENT_TITLE


def test_related_only_structured_article_does_not_override_page_metadata():
    related = old_record()
    # Even identical headline words do not override an explicitly different URL.
    related["headline"] = CURRENT_TITLE
    article = extract(related, extra_meta=(
        '<meta property="article:published_time" content="2026-10-29T05:00:00Z">'))
    assert article.text_content == CURRENT_BODY
    assert article.published_at == datetime(2026, 10, 29, 5, tzinfo=UTC)
    assert article.metadata["json_ld_article_detected"] is False


def test_hydration_selects_current_story_not_larger_recommendations_or_container():
    current = {"title": CURRENT_TITLE, "canonicalUrl": CURRENT_URL,
               "publishedAt": "2026-10-29T06:00:00Z", "body": CURRENT_BODY * 2}
    old = {"title": "Tennis champion remembers historic victory",
           "url": "https://news.example/sports/old-tennis-interview",
           "publishedAt": "2021-01-01T04:00:00Z", "body": OLD_BODY}
    article = extract(hydration={"props": {"pageProps": {
        "article": current, "recommendations": {"content": [old]},
    }}})
    assert article.title == CURRENT_TITLE
    assert article.published_at == datetime(2026, 10, 29, 6, tzinfo=UTC)
    assert "tennis" not in article.text_content
    assert article.extraction_method == "hydration_json_body"


def test_modification_date_does_not_make_old_publication_current():
    record = current_record()
    record["datePublished"] = "2021-01-01T04:00:00Z"
    record["dateModified"] = "2026-10-29T06:00:00Z"
    article = extract(record)
    assert article.published_at == datetime(2021, 1, 1, 4, tzinfo=UTC)
    assert article.modified_at == datetime(2026, 10, 29, 6, tzinfo=UTC)


def test_generic_page_date_and_modified_time_are_not_publication_evidence():
    article = extract(extra_meta=(
        '<meta name="date" content="2026-10-29T06:00:00Z">'
        '<meta name="dc.date" content="2026-10-29T06:00:00Z">'
        '<meta property="article:modified_time" content="2026-10-29T06:00:00Z">'))
    assert article.published_at is None
    assert article.modified_at == datetime(2026, 10, 29, 6, tzinfo=UTC)
    assert "missing_published_at" in article.warnings


def test_invalid_first_date_does_not_hide_later_publication_metadata():
    article = extract(extra_meta=(
        '<meta property="article:published_time" content="invalid-date">'
        '<meta property="article:published_time" content="2026-10-29T11:30:00+05:30">'
        '<meta name="pubdate" content="2026-10-29T06:00:00Z">'))
    assert article.published_at == datetime(2026, 10, 29, 6, tzinfo=UTC)


def test_metadata_inside_related_container_is_not_the_page_publication_date():
    html = (f'<html><head><meta property="og:title" content="{CURRENT_TITLE}"></head>'
            '<body><aside class="related"><meta itemprop="datePublished" '
            'content="2021-01-01T04:00:00Z"></aside>'
            f'<article><p>{CURRENT_BODY}</p></article></body></html>')
    article = extract_article_html(html.encode(), base_url=CURRENT_URL)
    assert article.published_at is None
    assert article.text_content == CURRENT_BODY


def test_same_headline_without_urls_is_ambiguous_and_uses_page_metadata():
    first, second = current_record(), current_record()
    del first["mainEntityOfPage"]
    del second["mainEntityOfPage"]
    second.update(articleBody=OLD_BODY, datePublished="2021-01-01T04:00:00Z")
    article = extract([first, second], extra_meta=(
        '<meta property="article:published_time" content="2026-10-29T06:00:00Z">'))
    assert article.text_content == CURRENT_BODY
    assert article.published_at == datetime(2026, 10, 29, 6, tzinfo=UTC)
    assert article.metadata["json_ld_article_detected"] is False


def test_content_query_parameters_identify_different_stories_but_tracking_does_not():
    first, second = current_record(), old_record()
    second.update(url=CURRENT_URL + "?story=related", headline=CURRENT_TITLE)
    article = extract([second, first])
    assert article.text_content == CURRENT_BODY
    assert article.metadata["publication_date_basis"] == "publisher_published"
    assert article.metadata["extraction_identity_policy"] == "page-identity-v2"


def test_embedded_entry_with_same_page_url_cannot_displace_page_headline():
    current, embedded = current_record(), old_record()
    embedded["url"] = CURRENT_URL + "#live-entry"
    article = extract([embedded, current])
    assert article.title == CURRENT_TITLE
    assert article.text_content == CURRENT_BODY
    assert article.published_at == datetime(2026, 10, 29, 4, tzinfo=UTC)
