import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from newsintel.adapters.collectors.feeds import (
    discover_websub_links,
    parse_feed_payload,
)
from newsintel.adapters.collectors.sitemaps import parse_sitemap
from newsintel.domain.acquisition.article_filter import looks_like_article_url
from newsintel.domain.acquisition.canonicalization import (
    CanonicalizationPolicy,
    canonicalize_url,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType

COMMON_DISCOVERY_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemapindex.xml",
    "/news-sitemap.xml",
    "/sitemap-news.xml",
    "/news_sitemap.xml",
    "/sitemap_news.xml",
    "/google-news-sitemap.xml",
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/index.xml",
    "/feed.json",
    "/index.json",
)


@dataclass(frozen=True, slots=True)
class DiscoveredEndpoint:
    url: str
    source: str
    hinted_type: DiscoveryChannelType | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidatedEndpoint:
    url: str
    channel_type: DiscoveryChannelType
    source: str
    item_count: int
    metadata: Mapping[str, object] = field(default_factory=dict)


class _AlternateLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.endpoints: list[DiscoveredEndpoint] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "link":
            return
        values = {key.lower(): (value or "").strip() for key, value in attrs}
        rel = values.get("rel", "").lower()
        href = values.get("href")
        link_type = values.get("type", "").lower().split(";", 1)[0].strip()
        if not href or "alternate" not in rel.split():
            return
        hinted = _channel_type_for_media_type(link_type)
        if hinted is None:
            return
        self.endpoints.append(
            DiscoveredEndpoint(
                url=urljoin(self.base_url, href),
                source="html_alternate",
                hinted_type=hinted,
                metadata={"media_type": link_type},
            )
        )


@dataclass(frozen=True, slots=True)
class HtmlArticleLink:
    url: str
    title: str | None
    published_at_raw: str | None = None
    structured_data: bool = False


class _AnchorLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[HtmlArticleLink] = []
        self.json_ld_scripts: list[str] = []
        self._href_stack: list[str | None] = []
        self._text_stack: list[list[str]] = []
        self._capture_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag_name = tag.lower()
        values = {key.lower(): (value or "").strip() for key, value in attrs}
        if tag_name == "script" and "ld+json" in values.get("type", "").lower():
            self._capture_json_ld = True
            self._json_ld_parts = []
            return
        if tag_name != "a":
            return
        href = values.get("href")
        if not href:
            return
        self._href_stack.append(urljoin(self.base_url, href))
        self._text_stack.append([])

    def handle_data(self, data: str) -> None:
        if self._capture_json_ld:
            self._json_ld_parts.append(data)
            return
        if self._text_stack:
            self._text_stack[-1].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name == "script" and self._capture_json_ld:
            payload = "".join(self._json_ld_parts).strip()
            if payload:
                self.json_ld_scripts.append(payload)
            self._capture_json_ld = False
            self._json_ld_parts = []
            return
        if tag_name != "a" or not self._href_stack:
            return
        href = self._href_stack.pop()
        text_parts = self._text_stack.pop() if self._text_stack else []
        if not href:
            return
        title = _normalize_text(" ".join(text_parts)) or None
        self.links.append(HtmlArticleLink(url=href, title=title))


def normalize_homepage_url(url: str) -> str:
    candidate = url.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    canonical = canonicalize_url(
        candidate,
        CanonicalizationPolicy(
            drop_parameters=frozenset(),
            strip_www=False,
        ),
    )
    return canonical.normalized


def canonical_domain(url: str) -> str:
    normalized = normalize_homepage_url(url)
    host = urlsplit(normalized).hostname
    if not host:
        raise ValueError("website URL must include a hostname")
    return host.lower()


def origin_for_url(url: str) -> str:
    parsed = urlsplit(normalize_homepage_url(url))
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def discover_alternate_links(
    html: bytes,
    *,
    homepage_url: str,
) -> tuple[DiscoveredEndpoint, ...]:
    parser = _AlternateLinkParser(homepage_url)
    parser.feed(_decode_html(html))
    parser.close()
    return tuple(parser.endpoints)


def discover_http_link_endpoints(
    headers: Mapping[str, str],
    *,
    base_url: str,
) -> tuple[DiscoveredEndpoint, ...]:
    """Discover syndication feeds advertised through HTTP Link headers."""
    raw = headers.get("link") or headers.get("Link")
    if not raw:
        return ()
    endpoints: list[DiscoveredEndpoint] = []
    for value in _split_link_header(raw):
        if not value.startswith("<") or ">" not in value:
            continue
        target, raw_params = value[1:].split(">", 1)
        params: dict[str, str] = {}
        for raw_param in raw_params.split(";"):
            if "=" not in raw_param:
                continue
            key, val = raw_param.split("=", 1)
            params[key.strip().lower()] = val.strip().strip('"')
        rel_tokens = {item.lower() for item in params.get("rel", "").split()}
        if "alternate" not in rel_tokens:
            continue
        media_type = params.get("type", "").lower().split(";", 1)[0].strip()
        hinted = _channel_type_for_media_type(media_type)
        if hinted is None:
            continue
        endpoints.append(
            DiscoveredEndpoint(
                url=urljoin(base_url, target.strip()),
                source="http_link_header",
                hinted_type=hinted,
                metadata={"media_type": media_type},
            )
        )
    return tuple(endpoints)


def discover_robot_sitemaps(
    robots_txt: bytes,
    *,
    homepage_url: str,
) -> tuple[DiscoveredEndpoint, ...]:
    endpoints: list[DiscoveredEndpoint] = []
    for raw_line in _decode_html(robots_txt).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        if key.strip().lower() != "sitemap":
            continue
        sitemap_url = value.strip()
        if sitemap_url:
            resolved = urljoin(homepage_url, sitemap_url)
            endpoints.append(
                DiscoveredEndpoint(
                    url=resolved,
                    source="robots_txt",
                    hinted_type=infer_sitemap_channel_type(resolved),
                )
            )
    return tuple(endpoints)


def common_discovery_endpoints(homepage_url: str) -> tuple[DiscoveredEndpoint, ...]:
    origin = origin_for_url(homepage_url)
    endpoints: list[DiscoveredEndpoint] = []
    for path in COMMON_DISCOVERY_PATHS:
        if "sitemap" in path:
            hinted = infer_sitemap_channel_type(path)
        elif path.endswith(".json"):
            hinted = DiscoveryChannelType.JSON_FEED
        elif "atom" in path:
            hinted = DiscoveryChannelType.ATOM
        else:
            hinted = DiscoveryChannelType.RSS
        endpoints.append(
            DiscoveredEndpoint(
                url=urljoin(origin, path),
                source="common_path",
                hinted_type=hinted,
            )
        )
    return tuple(endpoints)



def discover_syndication_directory_endpoints(
    html: bytes,
    *,
    page_url: str,
    max_endpoints: int = 50,
) -> tuple[DiscoveredEndpoint, ...]:
    """Discover feed links advertised from an HTML RSS/feed directory.

    Some publishers use paths such as ``/rss`` as a human-facing directory rather
    than as an XML feed.  This parser intentionally requires multiple feed signals
    before following a cross-origin link (for example FeedBurner), so a generic
    navigation page does not turn into an unbounded external crawl.
    """
    parser = _AnchorLinkParser(page_url)
    parser.feed(_decode_html(html))
    parser.close()
    page_host = (urlsplit(page_url).hostname or "").casefold()
    scored: list[tuple[int, DiscoveredEndpoint]] = []
    seen: set[str] = set()

    for link in parser.links:
        try:
            parsed = urlsplit(link.url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            target_host = parsed.hostname.casefold()
            normalized = canonicalize_url(
                link.url,
                CanonicalizationPolicy(drop_parameters=frozenset()),
            ).normalized
        except ValueError:
            continue
        if normalized in seen:
            continue

        haystack = f"{parsed.path} {parsed.query} {link.title or ''}".casefold()
        score = 0
        if any(term in haystack for term in ("rss", "atom", "feed", "syndicat")):
            score += 2
        if target_host.startswith("feeds.") or "feedburner" in target_host or "feedproxy" in target_host:
            score += 3
        if parsed.path.casefold().endswith((".rss", ".xml", ".atom", ".json")):
            score += 2
        if target_host == page_host:
            score += 1

        # Cross-origin links need stronger evidence than same-origin feed links.
        minimum = 3 if target_host != page_host else 2
        if score < minimum:
            continue

        hinted = _feed_hint_from_url_and_title(normalized, link.title)
        seen.add(normalized)
        scored.append(
            (
                score,
                DiscoveredEndpoint(
                    url=normalized,
                    source="html_feed_directory",
                    hinted_type=hinted,
                    metadata={
                        "directory_url": page_url,
                        "anchor_text": (link.title or "")[:200],
                    },
                ),
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1].url))
    return tuple(item[1] for item in scored[:max_endpoints])

def discover_html_article_links(
    html: bytes,
    *,
    page_url: str,
    same_origin_only: bool = True,
) -> tuple[HtmlArticleLink, ...]:
    parser = _AnchorLinkParser(page_url)
    parser.feed(_decode_html(html))
    parser.close()
    page_origin = origin_for_url(page_url)
    by_url: dict[str, HtmlArticleLink] = {}

    for link in parser.links:
        try:
            if same_origin_only and origin_for_url(link.url) != page_origin:
                continue
            if not looks_like_article_url(link.url):
                continue
            normalized = canonicalize_url(link.url).normalized
        except ValueError:
            continue
        by_url.setdefault(
            normalized,
            HtmlArticleLink(url=normalized, title=link.title),
        )

    for link in _structured_article_links(parser.json_ld_scripts, base_url=page_url):
        try:
            if same_origin_only and origin_for_url(link.url) != page_origin:
                continue
            normalized = canonicalize_url(link.url).normalized
        except ValueError:
            continue
        existing = by_url.get(normalized)
        by_url[normalized] = HtmlArticleLink(
            url=normalized,
            title=link.title or (existing.title if existing else None),
            published_at_raw=(
                link.published_at_raw
                or (existing.published_at_raw if existing else None)
            ),
            structured_data=True,
        )

    return tuple(by_url.values())


def discover_listing_endpoints(
    html: bytes,
    *,
    homepage_url: str,
    max_endpoints: int = 20,
) -> tuple[DiscoveredEndpoint, ...]:
    """Discover likely news listing pages using URL and navigation-label evidence."""
    parser = _AnchorLinkParser(homepage_url)
    parser.feed(_decode_html(html))
    parser.close()
    page_origin = origin_for_url(homepage_url)
    seen: set[str] = set()
    scored: list[tuple[int, DiscoveredEndpoint]] = []
    for link in parser.links:
        try:
            if origin_for_url(link.url) != page_origin:
                continue
            score = _listing_page_score(link.url, link.title)
            if score < 2:
                continue
            normalized = canonicalize_url(
                link.url,
                CanonicalizationPolicy(drop_parameters=frozenset()),
            ).normalized
        except ValueError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        channel_type = _listing_channel_type(normalized)
        scored.append(
            (
                score,
                DiscoveredEndpoint(
                    url=normalized,
                    source="homepage_listing_link",
                    hinted_type=channel_type,
                    metadata={"listing_score": str(score)},
                ),
            )
        )
    scored.sort(key=lambda item: -item[0])
    return tuple(item[1] for item in scored[:max_endpoints])


def unique_endpoints(
    endpoints: tuple[DiscoveredEndpoint, ...],
) -> tuple[DiscoveredEndpoint, ...]:
    """Canonicalize and merge duplicate endpoint evidence without losing provenance."""
    output: list[DiscoveredEndpoint] = []
    positions: dict[str, int] = {}
    for endpoint in endpoints:
        try:
            normalized = canonicalize_url(
                endpoint.url,
                CanonicalizationPolicy(drop_parameters=frozenset()),
            ).normalized
        except ValueError:
            continue
        existing_index = positions.get(normalized)
        if existing_index is None:
            positions[normalized] = len(output)
            output.append(
                DiscoveredEndpoint(
                    url=normalized,
                    source=endpoint.source,
                    hinted_type=endpoint.hinted_type,
                    metadata=dict(endpoint.metadata),
                )
            )
            continue
        existing = output[existing_index]
        sources = "+".join(dict.fromkeys((*existing.source.split("+"), endpoint.source)))
        hinted = _prefer_channel_hint(existing.hinted_type, endpoint.hinted_type)
        merged_metadata = dict(existing.metadata)
        merged_metadata.update(endpoint.metadata)
        output[existing_index] = DiscoveredEndpoint(
            url=normalized,
            source=sources,
            hinted_type=hinted,
            metadata=merged_metadata,
        )
    return tuple(output)


def validate_endpoint_payload(
    payload: bytes,
    *,
    endpoint_url: str,
    source: str,
    hinted_type: DiscoveryChannelType | None = None,
) -> ValidatedEndpoint:
    if hinted_type in _HTML_DISCOVERY_CHANNEL_TYPES:
        article_links = discover_html_article_links(payload, page_url=endpoint_url)
        if article_links:
            return ValidatedEndpoint(
                url=endpoint_url,
                channel_type=hinted_type,
                source=source,
                item_count=len(article_links),
            )

    feed_error: Exception | None = None
    try:
        feed_items = parse_feed_payload(payload, endpoint_url)
        if feed_items:
            channel_type = feed_items[0].channel_type
            metadata: dict[str, object] = {}
            if channel_type in {DiscoveryChannelType.RSS, DiscoveryChannelType.ATOM}:
                try:
                    hubs, self_url = discover_websub_links(payload)
                except Exception:
                    hubs, self_url = (), None
                if hubs:
                    metadata["websub_hubs"] = list(hubs)
                if self_url:
                    metadata["websub_self_url"] = self_url
            return ValidatedEndpoint(
                url=endpoint_url,
                channel_type=channel_type,
                source=source,
                item_count=len(feed_items),
                metadata=metadata,
            )
    except Exception as exc:
        feed_error = exc

    try:
        sitemap = parse_sitemap(payload)
        if sitemap.entries:
            channel_type = (
                DiscoveryChannelType.NEWS_SITEMAP
                if sitemap.contains_news
                else DiscoveryChannelType.SITEMAP
            )
            return ValidatedEndpoint(
                url=endpoint_url,
                channel_type=channel_type,
                source=source,
                item_count=len(sitemap.entries),
                metadata={
                    "sitemap_document_type": sitemap.document_type.value,
                    "contains_news": sitemap.contains_news,
                    "compressed": sitemap.compressed,
                },
            )
    except Exception as sitemap_error:
        if feed_error is not None:
            raise ValueError(
                f"endpoint is neither valid feed nor sitemap: {feed_error}; {sitemap_error}"
            ) from sitemap_error
        raise

    raise ValueError("endpoint parsed but did not contain items")


def infer_sitemap_channel_type(
    url: str,
    *,
    parent_type: DiscoveryChannelType | None = None,
) -> DiscoveryChannelType:
    if parent_type is DiscoveryChannelType.NEWS_SITEMAP:
        return DiscoveryChannelType.NEWS_SITEMAP
    if parent_type is DiscoveryChannelType.SITEMAP:
        return DiscoveryChannelType.SITEMAP
    path = urlsplit(url).path.lower()
    filename = path.rsplit("/", 1)[-1]
    if "news" in filename:
        return DiscoveryChannelType.NEWS_SITEMAP
    return DiscoveryChannelType.SITEMAP


def _structured_article_links(
    scripts: list[str],
    *,
    base_url: str,
) -> tuple[HtmlArticleLink, ...]:
    output: list[HtmlArticleLink] = []
    for script in scripts:
        try:
            payload: Any = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(payload):
            types = item.get("@type")
            if isinstance(types, str):
                normalized_types = {types.casefold()}
            elif isinstance(types, list):
                normalized_types = {str(value).casefold() for value in types}
            else:
                normalized_types = set()
            if not normalized_types & {
                "article",
                "newsarticle",
                "reportagenewsarticle",
                "analysisnewsarticle",
                "blogposting",
            }:
                continue
            article_url = _json_ld_article_url(item)
            if not article_url:
                continue
            headline = item.get("headline") or item.get("name")
            published = item.get("datePublished")
            output.append(
                HtmlArticleLink(
                    url=urljoin(base_url, article_url),
                    title=(
                        _normalize_text(headline)
                        if isinstance(headline, str)
                        else None
                    ),
                    published_at_raw=(
                        published.strip()
                        if isinstance(published, str) and published.strip()
                        else None
                    ),
                    structured_data=True,
                )
            )
    return tuple(output)


def _walk_json_ld(value: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            output.extend(_walk_json_ld(item))
        return output
    if not isinstance(value, dict):
        return output
    output.append(value)
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            output.extend(_walk_json_ld(item))
    return output


def _json_ld_article_url(item: Mapping[str, Any]) -> str | None:
    direct = item.get("url")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    main = item.get("mainEntityOfPage")
    if isinstance(main, str) and main.strip():
        return main.strip()
    if isinstance(main, Mapping):
        identifier = main.get("@id") or main.get("url")
        if isinstance(identifier, str) and identifier.strip():
            return identifier.strip()
    identifier = item.get("@id")
    if isinstance(identifier, str) and identifier.strip().startswith(("http://", "https://", "/")):
        return identifier.strip()
    return None


def _decode_html(payload: bytes) -> str:
    for encoding in ("utf-8", "windows-1252", "iso-8859-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")



def _feed_hint_from_url_and_title(
    url: str,
    title: str | None,
) -> DiscoveryChannelType:
    text = f"{url} {title or ''}".casefold()
    if "atom" in text:
        return DiscoveryChannelType.ATOM
    if urlsplit(url).path.casefold().endswith(".json") or "json feed" in text:
        return DiscoveryChannelType.JSON_FEED
    return DiscoveryChannelType.RSS

def _channel_type_for_media_type(media_type: str) -> DiscoveryChannelType | None:
    if media_type in {"application/rss+xml", "application/rdf+xml"}:
        return DiscoveryChannelType.RSS
    if media_type == "application/atom+xml":
        return DiscoveryChannelType.ATOM
    if media_type == "application/feed+json":
        return DiscoveryChannelType.JSON_FEED
    return None


def _split_link_header(value: str) -> tuple[str, ...]:
    parts: list[str] = []
    start = 0
    in_quotes = False
    angle_depth = 0
    for index, char in enumerate(value):
        if char == '"':
            in_quotes = not in_quotes
        elif not in_quotes and char == "<":
            angle_depth += 1
        elif not in_quotes and char == ">" and angle_depth:
            angle_depth -= 1
        elif char == "," and not in_quotes and angle_depth == 0:
            part = value[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return tuple(parts)


_HTML_DISCOVERY_CHANNEL_TYPES = {
    DiscoveryChannelType.HOMEPAGE,
    DiscoveryChannelType.CATEGORY,
    DiscoveryChannelType.TAG,
    DiscoveryChannelType.AUTHOR,
    DiscoveryChannelType.ARCHIVE,
    DiscoveryChannelType.INTERNAL_LINK,
    DiscoveryChannelType.SEARCH,
}

_LISTING_HINT_SEGMENTS = {
    "ai",
    "artificial-intelligence",
    "business",
    "cities",
    "city",
    "climate",
    "economy",
    "election",
    "elections",
    "finance",
    "health",
    "healthcare",
    "india",
    "international",
    "latest",
    "latest-news",
    "markets",
    "national",
    "news",
    "politics",
    "science",
    "space",
    "state",
    "states",
    "sport",
    "sports",
    "tech",
    "technology",
    "world",
    "world-news",
}
_LISTING_TITLE_HINTS = {
    "business",
    "cities",
    "climate",
    "economy",
    "elections",
    "finance",
    "health",
    "india",
    "international",
    "latest",
    "latest news",
    "markets",
    "national",
    "news",
    "politics",
    "science",
    "sports",
    "technology",
    "world",
    "भारत",
    "देश",
    "दुनिया",
    "खेल",
    "राज्य",
    "समाचार",
    "तकनीक",
    "व्यापार",
}
_LISTING_EXCLUDED_SEGMENTS = {
    "about",
    "account",
    "advertise",
    "contact",
    "login",
    "privacy",
    "signin",
    "subscribe",
    "terms",
}


def _listing_page_score(url: str, title: str | None = None) -> int:
    if looks_like_article_url(url):
        return 0
    parsed = urlsplit(url)
    path = parsed.path.lower().strip("/")
    if not path:
        return 0
    segments = [segment for segment in path.split("/") if segment]
    if not segments or len(segments) > 4:
        return 0
    if set(segments) & _LISTING_EXCLUDED_SEGMENTS:
        return 0

    score = 0
    has_path_hint = bool(set(segments) & _LISTING_HINT_SEGMENTS)
    if has_path_hint:
        score += 2
    if set(segments) & {"author", "authors", "tag", "tags", "archive", "archives"}:
        score += 2
    normalized_title = _normalize_text(title).casefold()
    if (
        not has_path_hint
        and normalized_title
        and any(
            hint.casefold() == normalized_title or hint.casefold() in normalized_title
            for hint in _LISTING_TITLE_HINTS
        )
    ):
        score += 2
    if len(segments) <= 2:
        score += 1
    if parsed.query:
        score -= 1
    return score


def _listing_channel_type(url: str) -> DiscoveryChannelType:
    segments = {segment for segment in urlsplit(url).path.lower().split("/") if segment}
    if segments & {"tag", "tags"}:
        return DiscoveryChannelType.TAG
    if segments & {"author", "authors"}:
        return DiscoveryChannelType.AUTHOR
    if segments & {"archive", "archives"}:
        return DiscoveryChannelType.ARCHIVE
    return DiscoveryChannelType.CATEGORY


def _prefer_channel_hint(
    first: DiscoveryChannelType | None,
    second: DiscoveryChannelType | None,
) -> DiscoveryChannelType | None:
    if first is None:
        return second
    if second is None:
        return first
    priorities = {
        DiscoveryChannelType.NEWS_SITEMAP: 100,
        DiscoveryChannelType.JSON_FEED: 90,
        DiscoveryChannelType.ATOM: 80,
        DiscoveryChannelType.RSS: 70,
        DiscoveryChannelType.SITEMAP: 60,
        DiscoveryChannelType.HOMEPAGE: 50,
        DiscoveryChannelType.CATEGORY: 40,
        DiscoveryChannelType.TAG: 30,
        DiscoveryChannelType.AUTHOR: 30,
        DiscoveryChannelType.ARCHIVE: 20,
    }
    return max((first, second), key=lambda item: priorities.get(item, 0))


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split()).strip()
