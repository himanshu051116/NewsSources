from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from gzip import GzipFile
from io import BytesIO
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

NEWS_NAMESPACE = "http://www.google.com/schemas/sitemap-news/0.9"
DEFAULT_MAX_DECOMPRESSED_BYTES = 32_000_000


class SitemapDocumentType(StrEnum):
    URL_SET = "urlset"
    INDEX = "sitemapindex"


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    location: str
    last_modified_raw: str | None
    publication_date_raw: str | None = None
    news_title: str | None = None
    news_publication_name: str | None = None
    news_language: str | None = None
    is_news: bool = False


@dataclass(frozen=True, slots=True)
class SitemapDocument:
    document_type: SitemapDocumentType
    entries: tuple[SitemapEntry, ...]
    parsed_at: datetime
    contains_news: bool = False
    compressed: bool = False


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _namespace_uri(tag: str) -> str | None:
    if not tag.startswith("{") or "}" not in tag:
        return None
    return tag[1:].split("}", 1)[0]


def _first_descendant_text(
    element: Element,
    local_name: str,
    *,
    namespace: str | None = None,
) -> str | None:
    for descendant in element.iter():
        if _local_name(descendant.tag) != local_name:
            continue
        if namespace is not None and _namespace_uri(descendant.tag) != namespace:
            continue
        if descendant.text:
            value = str(descendant.text).strip()
            if value:
                return value
    return None


def _news_element(element: Element) -> Element | None:
    for descendant in element.iter():
        if (
            _local_name(descendant.tag) == "news"
            and _namespace_uri(descendant.tag) == NEWS_NAMESPACE
        ):
            return descendant
    return None


def _decompress_if_needed(
    xml: str | bytes,
    *,
    max_decompressed_bytes: int = DEFAULT_MAX_DECOMPRESSED_BYTES,
) -> tuple[str | bytes, bool]:
    if isinstance(xml, str):
        return xml, False
    if not xml.startswith(b"\x1f\x8b"):
        return xml, False
    with GzipFile(fileobj=BytesIO(xml)) as stream:
        payload = stream.read(max_decompressed_bytes + 1)
    if len(payload) > max_decompressed_bytes:
        raise ValueError("decompressed sitemap exceeded configured byte limit")
    return payload, True


def parse_sitemap(xml: str | bytes) -> SitemapDocument:
    payload, compressed = _decompress_if_needed(xml)
    root = ElementTree.fromstring(payload)
    root_name = _local_name(root.tag)
    if root_name not in {"urlset", "sitemapindex"}:
        raise ValueError(f"unsupported sitemap root element: {root_name}")

    child_name = "url" if root_name == "urlset" else "sitemap"
    entries: list[SitemapEntry] = []
    contains_news = False
    for element in root:
        if _local_name(element.tag) != child_name:
            continue
        location = _first_descendant_text(element, "loc")
        if not location:
            continue

        news_element = _news_element(element) if root_name == "urlset" else None
        is_news = news_element is not None
        contains_news = contains_news or is_news
        publication_date = (
            _first_descendant_text(
                news_element,
                "publication_date",
                namespace=NEWS_NAMESPACE,
            )
            if news_element is not None
            else None
        )
        news_title = (
            _first_descendant_text(news_element, "title", namespace=NEWS_NAMESPACE)
            if news_element is not None
            else None
        )
        publication_name = None
        language = None
        if news_element is not None:
            for descendant in news_element.iter():
                if (
                    _local_name(descendant.tag) == "publication"
                    and _namespace_uri(descendant.tag) == NEWS_NAMESPACE
                ):
                    publication_name = _first_descendant_text(
                        descendant,
                        "name",
                        namespace=NEWS_NAMESPACE,
                    )
                    language = _first_descendant_text(
                        descendant,
                        "language",
                        namespace=NEWS_NAMESPACE,
                    )
                    break

        entries.append(
            SitemapEntry(
                location=location,
                last_modified_raw=_first_descendant_text(element, "lastmod"),
                publication_date_raw=publication_date,
                news_title=news_title,
                news_publication_name=publication_name,
                news_language=language,
                is_news=is_news,
            )
        )
    return SitemapDocument(
        document_type=(
            SitemapDocumentType.URL_SET
            if root_name == "urlset"
            else SitemapDocumentType.INDEX
        ),
        entries=tuple(entries),
        parsed_at=datetime.now(UTC),
        contains_news=contains_news,
        compressed=compressed,
    )
