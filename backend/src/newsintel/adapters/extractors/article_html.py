from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from importlib import import_module
from typing import Any
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

_WHITESPACE_PATTERN = re.compile(r"\s+")
_ATTRIBUTE_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "reportagenewsarticle",
    "analysisnewsarticle",
    "blogposting",
}
_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
    "select",
    "textarea",
}
_BLOCK_TAGS = {
    "p",
    "li",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
_LOW_VALUE_PHRASES = (
    "account subscription benefits",
    "accept cookies",
    "active subscription",
    "all rights reserved",
    "click here",
    "continue reading",
    "enable javascript",
    "founder summit",
    "join 1,000+ founders",
    "loading...",
    "logout and login",
    "premium stories",
    "privacy policy",
    "register now",
    "sign in",
    "strictlyvc",
    "subscribed with another email",
    "subscribe now",
    "ticket savings",
    "tickets are going fast",
    "terms of use",
    "you don't have any active subscription",
)
_PAYWALL_OR_ACCOUNT_PHRASES = (
    "active subscription",
    "already a subscriber",
    "continue reading with",
    "for subscribers",
    "login with that one",
    "metered access",
    "premium stories",
    "subscribe to continue",
    "subscribe now",
    "subscriber only",
    "subscription required",
)
_SKIP_ATTRIBUTE_TOKENS = {
    "ad",
    "ads",
    "advert",
    "advertisement",
    "banner",
    "comments",
    "consent",
    "cookie",
    "footer",
    "gallery",
    "header",
    "login",
    "modal",
    "newsletter",
    "paywall",
    "promo",
    "promoted",
    "recommend",
    "related",
    "share",
    "signin",
    "social",
    "sponsor",
    "sponsored",
    "subscription",
    "video",
}
_SKIP_ATTRIBUTE_PHRASES = (
    "more from",
    "paid post",
    "read more",
    "related content",
    "share this",
    "sign in",
    "subscribe",
)


@dataclass(frozen=True, slots=True)
class ExtractionProfile:
    """Publisher-specific extraction hints loaded from durable configuration.

    These hints affect extraction selection/boilerplate filtering only. They never
    bypass crawler access controls or subscriber-only content boundaries.
    """

    name: str
    preferred_method: str = "auto"
    recommended_method: str | None = None
    low_value_phrases: tuple[str, ...] = ()
    skip_attribute_tokens: frozenset[str] = frozenset()
    skip_attribute_phrases: tuple[str, ...] = ()
    paywall_or_partial_phrases: tuple[str, ...] = ()
    browser_render_enabled: bool = False
    browser_allowed_domains: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ExtractionPolicy:
    name: str
    domain_suffixes: tuple[str, ...]
    low_value_phrases: tuple[str, ...] = ()
    skip_attribute_tokens: frozenset[str] = frozenset()
    skip_attribute_phrases: tuple[str, ...] = ()
    paywall_or_partial_phrases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _OptionalExtractorResult:
    text: str
    method: str
    metadata: dict[str, object]


_PUBLISHER_POLICIES = (
    _ExtractionPolicy(
        name="techcrunch",
        domain_suffixes=("techcrunch.com",),
        low_value_phrases=(
            "strictlyvc",
            "founder summit",
            "join 1,000+ founders",
            "tickets are going fast",
        ),
        skip_attribute_tokens=frozenset({"event", "events", "promo", "sponsor"}),
    ),
    _ExtractionPolicy(
        name="the_hindu",
        domain_suffixes=("thehindu.com", "www.thehindu.com"),
        low_value_phrases=(
            "account subscription benefits",
            "active subscription",
            "premium stories",
            "subscribed with another email",
        ),
        skip_attribute_tokens=frozenset({"subscription", "paywall", "premium"}),
        paywall_or_partial_phrases=(
            "you don't have any active subscription",
            "premium stories",
        ),
    ),
    _ExtractionPolicy(
        name="indian_express",
        domain_suffixes=("indianexpress.com", "www.indianexpress.com"),
        low_value_phrases=("subscribe to continue", "premium article"),
        skip_attribute_tokens=frozenset({"premium", "subscription", "paywall"}),
    ),
    _ExtractionPolicy(
        name="ndtv",
        domain_suffixes=("ndtv.com", "www.ndtv.com"),
        skip_attribute_tokens=frozenset({"also", "related", "video"}),
        skip_attribute_phrases=("also read", "related stories"),
    ),
)


@dataclass(frozen=True, slots=True)
class ExtractedArticle:
    title: str | None
    byline: str | None
    published_at: datetime | None
    modified_at: datetime | None
    language: str | None
    canonical_url: str | None
    text_content: str
    content_sha256: str
    extraction_method: str
    metadata: dict[str, object]
    warnings: tuple[str, ...]

    @property
    def word_count(self) -> int:
        return len(self.text_content.split())


@dataclass(slots=True)
class _TextBlock:
    tag: str
    pieces: list[str]


@dataclass(frozen=True, slots=True)
class _ParagraphExtractionResult:
    text: str
    accepted_block_count: int
    rejected_block_count: int
    rejected_boilerplate_count: int
    rejected_short_count: int


class _ArticleHTMLParser(HTMLParser):
    def __init__(self, base_url: str, *, policy: _ExtractionPolicy | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.policy = policy
        self.title_parts: list[str] = []
        self.blocks: list[str] = []
        self.meta: dict[str, list[str]] = {}
        self.links: dict[str, str] = {}
        self.outbound_links: list[str] = []
        self.json_ld_scripts: list[str] = []
        self.hydration_json_scripts: list[str] = []
        self.html_language: str | None = None

        self._skip_depth = 0
        self._skip_stack: list[str] = []
        self._in_title = False
        self._capture_json_ld = False
        self._capture_hydration_json = False
        self._script_parts: list[str] = []
        self._hydration_parts: list[str] = []
        self._block_stack: list[_TextBlock] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag_name = tag.lower()
        attr_map = {
            key.lower(): value.strip() if value is not None else ""
            for key, value in attrs
        }

        if tag_name == "html":
            language = attr_map.get("lang") or attr_map.get("xml:lang")
            if language:
                self.html_language = language

        if tag_name == "title":
            self._in_title = True

        if tag_name == "meta" and self._skip_depth == 0:
            content = attr_map.get("content")
            key = (
                attr_map.get("property")
                or attr_map.get("name")
                or attr_map.get("itemprop")
                or attr_map.get("http-equiv")
            )
            if key and content:
                self.meta.setdefault(key.lower(), []).append(content)

        if tag_name == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href")
            if href:
                for relation in rel.split():
                    self.links[relation] = urljoin(self.base_url, href)

        if tag_name == "a" and self._skip_depth == 0:
            href = attr_map.get("href")
            if href:
                self.outbound_links.append(urljoin(self.base_url, href))

        if tag_name == "script":
            script_type = attr_map.get("type", "").lower()
            script_id = attr_map.get("id", "").casefold()
            if "ld+json" in script_type:
                self._capture_json_ld = True
                self._script_parts = []
            elif (
                "application/json" in script_type
                or script_id in {"__next_data__", "__nuxt_data__", "__apollo_state__"}
            ):
                self._capture_hydration_json = True
                self._hydration_parts = []

        if tag_name in _SKIP_TAGS or _should_skip_by_attributes(
            tag_name,
            attr_map,
            policy=self.policy,
        ):
            self._skip_depth += 1
            self._skip_stack.append(tag_name)
            return

        if self._skip_depth == 0 and tag_name in _BLOCK_TAGS:
            self._block_stack.append(_TextBlock(tag=tag_name, pieces=[]))

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()

        if tag_name == "title":
            self._in_title = False

        if tag_name == "script" and self._capture_json_ld:
            script = "".join(self._script_parts).strip()
            if script:
                self.json_ld_scripts.append(script)
            self._capture_json_ld = False
            self._script_parts = []

        if tag_name == "script" and self._capture_hydration_json:
            script = "".join(self._hydration_parts).strip()
            if script and len(script) <= 2_000_000:
                self.hydration_json_scripts.append(script)
            self._capture_hydration_json = False
            self._hydration_parts = []

        if self._skip_depth > 0 and tag_name in self._skip_stack:
            while self._skip_stack:
                skipped_tag = self._skip_stack.pop()
                self._skip_depth -= 1
                if skipped_tag == tag_name:
                    break
            return

        if tag_name in _BLOCK_TAGS and self._block_stack:
            index = next(
                (
                    position
                    for position in range(len(self._block_stack) - 1, -1, -1)
                    if self._block_stack[position].tag == tag_name
                ),
                None,
            )
            if index is None:
                return
            block = self._block_stack.pop(index)
            text = _normalize_text(" ".join(block.pieces))
            if text:
                self.blocks.append(text)
                if self._block_stack:
                    self._block_stack[-1].pieces.append(text)

    def handle_data(self, data: str) -> None:
        if self._capture_json_ld:
            self._script_parts.append(data)
            return
        if self._capture_hydration_json:
            if sum(len(part) for part in self._hydration_parts) < 2_000_000:
                self._hydration_parts.append(data)
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._skip_depth > 0:
            return
        if self._block_stack:
            self._block_stack[-1].pieces.append(data)


def extract_article_html(
    html: bytes,
    *,
    base_url: str,
    profile: ExtractionProfile | None = None,
) -> ExtractedArticle:
    policy = _effective_policy(base_url, profile)
    parser = _ArticleHTMLParser(base_url, policy=policy)
    decoded = _decode_html(html)
    parser.feed(decoded)
    parser.close()

    page_title = _first_present(
        _first_meta(parser.meta, "og:title", "twitter:title", "parsely-title", "dc.title", "title"),
        _normalize_text(" ".join(parser.title_parts)),
    )
    canonical_url = _first_present(
        parser.links.get("canonical"),
        _first_meta(parser.meta, "og:url", "twitter:url"),
    )
    page_urls = (base_url, canonical_url) if canonical_url else (base_url,)
    json_ld_objects = tuple(_iter_json_ld_objects(parser.json_ld_scripts))
    json_ld_article = _select_article_json_ld(
        json_ld_objects, page_urls=page_urls, page_title=page_title,
    )
    json_ld_body = _string_value(json_ld_article.get("articleBody")) if json_ld_article else None
    hydration_objects = tuple(_iter_hydration_objects(parser.hydration_json_scripts))
    hydration_article = _select_hydration_article(
        hydration_objects, page_urls=page_urls,
        page_title=page_title or (_string_value(json_ld_article.get("headline"))
                                  if json_ld_article else None),
    )
    hydration_body = _hydration_body(hydration_article) if hydration_article else None

    title = _first_present(
        _string_value(json_ld_article.get("headline")) if json_ld_article else None,
        _hydration_scalar(hydration_article, "headline", "title") if hydration_article else None,
        page_title,
    )
    byline = _first_present(
        _author_value(json_ld_article.get("author")) if json_ld_article else None,
        _hydration_author(hydration_article) if hydration_article else None,
        _first_meta(parser.meta, "author", "article:author", "parsely-author", "byl"),
    )
    published_at = _first_datetime(
        _string_value(json_ld_article.get("datePublished")) if json_ld_article else None,
        _hydration_scalar(
            hydration_article,
            "datePublished",
            "publishedAt",
            "published_at",
            "publishDate",
        ) if hydration_article else None,
        *_meta_values(
            parser.meta,
            "article:published_time",
            "datepublished",
            "dc.date.issued",
            "dcterms.issued",
            "pubdate",
            "sailthru.date",
            "parsely-pub-date",
        ),
    )
    modified_at = _first_datetime(
        _string_value(json_ld_article.get("dateModified")) if json_ld_article else None,
        _hydration_scalar(
            hydration_article,
            "dateModified",
            "modifiedAt",
            "updatedAt",
            "updated_at",
        ) if hydration_article else None,
        *_meta_values(
            parser.meta,
            "article:modified_time",
            "datemodified",
            "lastmod",
            "parsely-post-date",
        ),
    )
    language = _normalize_language(
        _first_present(
            _string_value(json_ld_article.get("inLanguage")) if json_ld_article else None,
            parser.html_language,
            _first_meta(parser.meta, "og:locale", "language", "content-language"),
        )
    )
    paragraph_result = _extract_paragraph_text(parser.blocks, policy=policy)
    optional_result = _extract_with_trafilatura(
        decoded,
        base_url=base_url,
        policy=policy,
    )
    trafilatura_available = optional_result is not None
    hydration_text = _normalize_multiline(hydration_body or "")
    hydration_available = len(hydration_text.split()) >= 50
    if json_ld_body and len(json_ld_body) >= 200:
        text_content = _normalize_multiline(json_ld_body)
        extraction_method = "json_ld_article_body"
        accepted_block_count = len([block for block in text_content.split("\n\n") if block])
        rejected_block_count = 0
        rejected_boilerplate_count = 0
        rejected_short_count = 0
    else:
        text_content = paragraph_result.text
        extraction_method = "visible_text_blocks"
        accepted_block_count = paragraph_result.accepted_block_count
        rejected_block_count = paragraph_result.rejected_block_count
        rejected_boilerplate_count = paragraph_result.rejected_boilerplate_count
        rejected_short_count = paragraph_result.rejected_short_count

        visible_quality_score = _extraction_quality_score(
            text_content,
            accepted_block_count=accepted_block_count,
            rejected_block_count=rejected_block_count,
            json_ld_article_detected=json_ld_article is not None,
        )
        if optional_result and _should_use_optional_extraction(
            current_text=text_content,
            current_quality_score=visible_quality_score,
            optional_text=optional_result.text,
        ):
            text_content = optional_result.text
            extraction_method = optional_result.method
            accepted_block_count = len(
                [block for block in text_content.split("\n\n") if block]
            )

        hydration_quality = _extraction_quality_score(
            hydration_text,
            accepted_block_count=len(
                [block for block in hydration_text.split("\n\n") if block]
            ),
            rejected_block_count=0,
            json_ld_article_detected=False,
        )
        current_quality = _extraction_quality_score(
            text_content,
            accepted_block_count=accepted_block_count,
            rejected_block_count=rejected_block_count,
            json_ld_article_detected=json_ld_article is not None,
        )
        preferred = _preferred_extraction_method(profile)
        if hydration_available and (
            (
                preferred == "hydration_json_body"
                and hydration_quality >= max(0.0, current_quality - 0.10)
            )
            or (
                current_quality < 0.55
                and hydration_quality >= current_quality
                and len(hydration_text.split()) >= len(text_content.split())
            )
            or len(hydration_text.split())
            >= round(max(1, len(text_content.split())) * 1.35)
        ):
            text_content = hydration_text
            extraction_method = "hydration_json_body"
            accepted_block_count = len(
                [block for block in text_content.split("\n\n") if block]
            )
            rejected_block_count = 0
            rejected_boilerplate_count = 0
            rejected_short_count = 0

        if preferred == "trafilatura_fallback" and optional_result:
            preferred_quality = _extraction_quality_score(
                optional_result.text,
                accepted_block_count=max(
                    1, len(optional_result.text.split("\n\n"))
                ),
                rejected_block_count=0,
                json_ld_article_detected=False,
            )
            current_quality = _extraction_quality_score(
                text_content,
                accepted_block_count=accepted_block_count,
                rejected_block_count=rejected_block_count,
                json_ld_article_detected=json_ld_article is not None,
            )
            if preferred_quality >= max(0.0, current_quality - 0.08):
                text_content = optional_result.text
                extraction_method = optional_result.method
                accepted_block_count = max(
                    1, len(text_content.split("\n\n"))
                )

    # Publisher headlines sometimes appear both in metadata and as the first visible
    # H1. Keeping that H1 inside the article body makes the claim extractor join a
    # non-sentence headline to the first factual sentence. Remove only an EXACT
    # first-block duplicate; never guess at near-matching editorial text.
    if title and text_content:
        first_block, separator, remainder = text_content.partition("\n\n")
        if separator and _normalize_text(first_block).casefold() == _normalize_text(title).casefold():
            text_content = remainder.strip()
            accepted_block_count = max(1, accepted_block_count - 1)

    quality_score = _extraction_quality_score(
        text_content,
        accepted_block_count=accepted_block_count,
        rejected_block_count=rejected_block_count,
        json_ld_article_detected=json_ld_article is not None,
    )

    warnings: list[str] = []
    if not title:
        warnings.append("missing_title")
    if not text_content:
        warnings.append("missing_text_content")
    elif len(text_content.split()) < 50:
        warnings.append("short_text_content")
    if not published_at:
        warnings.append("missing_published_at")
    if not canonical_url:
        warnings.append("missing_canonical_url")
    if rejected_boilerplate_count:
        warnings.append("boilerplate_removed")
    paywall_indicators = _matching_phrases(
        decoded,
        _paywall_or_partial_phrases(policy),
    )
    text_paywall_indicators = _matching_phrases(
        text_content,
        _paywall_or_partial_phrases(policy),
    )
    if text_paywall_indicators:
        warnings.append("possible_subscription_boilerplate")
    if _looks_partial_or_paywalled(
        word_count=len(text_content.split()),
        raw_indicators=paywall_indicators,
        text_indicators=text_paywall_indicators,
    ):
        warnings.append("possible_paywall_or_partial_content")
    if text_content and quality_score < 0.45:
        warnings.append("low_extraction_quality")

    raw_html_sha256 = sha256(html).hexdigest()
    candidate_quality_scores = _candidate_quality_scores(
        json_ld_body=json_ld_body,
        hydration_text=hydration_text,
        paragraph_result=paragraph_result,
        optional_result=optional_result,
        json_ld_article_detected=json_ld_article is not None,
    )
    metadata: dict[str, object] = {
        "html_title": _normalize_text(" ".join(parser.title_parts)) or None,
        "json_ld_object_count": len(json_ld_objects),
        "json_ld_article_detected": json_ld_article is not None,
        "hydration_json_object_count": len(hydration_objects),
        "hydration_article_detected": hydration_article is not None,
        "publisher_extraction_policy": policy.name if policy else "generic",
        "publisher_extraction_profile": profile.name if profile else None,
        "preferred_extraction_method": _preferred_extraction_method(profile),
        "candidate_quality_scores": candidate_quality_scores,
        "meta_keys": sorted(parser.meta.keys()),
        "publication_date_basis": "publisher_published" if published_at else "unconfirmed",
        "extraction_identity_policy": "page-identity-v2",
        "block_count": len(parser.blocks),
        "accepted_block_count": accepted_block_count,
        "rejected_block_count": rejected_block_count,
        "rejected_boilerplate_count": rejected_boilerplate_count,
        "rejected_short_count": rejected_short_count,
        "extraction_quality_score": quality_score,
        "optional_trafilatura_available": trafilatura_available,
        "raw_html_sha256": raw_html_sha256,
        "raw_html_bytes": len(html),
        "paywall_indicator_count": len(paywall_indicators),
        "paywall_indicators": list(paywall_indicators[:10]),
        "word_count": len(text_content.split()),
        "external_links": list(_external_article_links(parser.outbound_links, base_url)),
    }
    if optional_result:
        metadata["optional_trafilatura"] = optional_result.metadata
    if modified_at:
        metadata["modified_at"] = modified_at.isoformat()

    return ExtractedArticle(
        title=title,
        byline=byline,
        published_at=published_at,
        modified_at=modified_at,
        language=language,
        canonical_url=canonical_url,
        text_content=text_content,
        content_sha256=sha256(text_content.encode("utf-8")).hexdigest(),
        extraction_method=extraction_method,
        metadata=metadata,
        warnings=tuple(warnings),
    )


def _external_article_links(links: Iterable[str], base_url: str) -> tuple[str, ...]:
    base_host = (urlsplit(base_url).hostname or "").casefold()
    seen: set[str] = set()
    output: list[str] = []
    for raw in links:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if host == base_host or host.endswith(f".{base_host}") or base_host.endswith(f".{host}"):
            continue
        if _is_low_value_external_host(host):
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
        if len(output) >= 100:
            break
    return tuple(output)


def _is_low_value_external_host(host: str) -> bool:
    blocked_suffixes = (
        "facebook.com",
        "fb.com",
        "instagram.com",
        "linkedin.com",
        "t.me",
        "telegram.me",
        "twitter.com",
        "x.com",
        "youtube.com",
        "youtu.be",
        "whatsapp.com",
        "google.com",
        "googleapis.com",
        "doubleclick.net",
    )
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in blocked_suffixes)


def _decode_html(html: bytes) -> str:
    for encoding in ("utf-8", "windows-1252", "iso-8859-1"):
        try:
            return html.decode(encoding)
        except UnicodeDecodeError:
            continue
    return html.decode("utf-8", errors="replace")


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def _normalize_multiline(value: str) -> str:
    lines = [_normalize_text(line) for line in value.splitlines()]
    return "\n\n".join(line for line in lines if line)


def _first_meta(meta: Mapping[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        values = meta.get(key.lower(), [])
        for value in values:
            normalized = _normalize_text(value)
            if normalized:
                return normalized
    return None


def _meta_values(meta: Mapping[str, list[str]], *keys: str) -> Iterable[str]:
    for key in keys:
        yield from meta.get(key.lower(), [])


def _first_present(*values: str | None) -> str | None:
    for value in values:
        normalized = _normalize_text(value)
        if normalized:
            return normalized
    return None


def _first_datetime(*values: str | None) -> datetime | None:
    for value in values:
        parsed = _parse_datetime(value)
        if parsed:
            return parsed
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None

    iso_value = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _normalize_language(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    return normalized.replace("_", "-").split(",", maxsplit=1)[0][:35]


def _iter_hydration_objects(scripts: Iterable[str]) -> Iterable[dict[str, Any]]:
    emitted = 0
    for script in scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in _walk_hydration(payload, depth=0):
            yield item
            emitted += 1
            if emitted >= 5_000:
                return


def _walk_hydration(value: object, *, depth: int) -> Iterable[dict[str, Any]]:
    if depth > 12:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _walk_hydration(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value[:500]:
            if isinstance(child, (dict, list)):
                yield from _walk_hydration(child, depth=depth + 1)


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _hydration_scalar(item: Mapping[str, Any] | None, *keys: str) -> str | None:
    if item is None:
        return None
    wanted = {_normalized_key(key) for key in keys}
    for key, value in item.items():
        if _normalized_key(key) in wanted:
            scalar = _string_value(value)
            if scalar:
                return scalar
    return None


def _hydration_author(item: Mapping[str, Any] | None) -> str | None:
    if item is None:
        return None
    for key, value in item.items():
        if _normalized_key(key) in {"author", "authors", "byline"}:
            author = _author_value(value)
            if author:
                return author
    return None


def _hydration_body(item: Mapping[str, Any] | None) -> str | None:
    if item is None:
        return None
    body_keys = {
        "articlebody",
        "articlecontent",
        "body",
        "bodytext",
        "content",
        "story",
        "storybody",
        "storycontent",
        "text",
    }
    for key, value in item.items():
        if _normalized_key(key) not in body_keys:
            continue
        text = _hydration_text_payload(value, depth=0)
        if len(text.split()) >= 50:
            return text
    return None


def _hydration_text_payload(value: object, *, depth: int) -> str:
    if depth > 6:
        return ""
    if isinstance(value, str):
        raw = value
        if "<" in raw and ">" in raw:
            raw = re.sub(r"<[^>]+>", " ", raw)
            raw = unescape(raw)
        return _normalize_multiline(raw)
    if isinstance(value, list):
        parts = [_hydration_text_payload(item, depth=depth + 1) for item in value[:500]]
        return _normalize_multiline("\n\n".join(part for part in parts if part))
    if isinstance(value, dict):
        preferred: list[object] = []
        fallback: list[object] = []
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in {"text", "content", "body", "value", "html", "children"}:
                preferred.append(child)
            elif isinstance(child, (dict, list)):
                fallback.append(child)
        parts = [
            _hydration_text_payload(child, depth=depth + 1)
            for child in [*preferred, *fallback[:20]]
        ]
        return _normalize_multiline("\n\n".join(part for part in parts if part))
    return ""


def _select_hydration_article(
    objects: Iterable[Mapping[str, Any]],
    *,
    page_urls: tuple[str, ...],
    page_title: str | None,
) -> Mapping[str, Any] | None:
    candidates: list[Mapping[str, Any]] = []
    for item in objects:
        body = _hydration_body(item)
        if not body:
            continue
        # Containers of recommended stories can aggregate into a longer body
        # than the actual article. They are not article records themselves.
        if not _hydration_scalar(item, "headline", "title"):
            continue
        candidates.append(item)
    return _select_page_article(candidates, page_urls=page_urls, page_title=page_title)


def _preferred_extraction_method(profile: ExtractionProfile | None) -> str:
    if profile is None:
        return "auto"
    if profile.preferred_method != "auto":
        return profile.preferred_method
    return profile.recommended_method or "auto"


def _candidate_quality_scores(
    *,
    json_ld_body: str | None,
    hydration_text: str,
    paragraph_result: _ParagraphExtractionResult,
    optional_result: _OptionalExtractorResult | None,
    json_ld_article_detected: bool,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    if json_ld_body:
        text = _normalize_multiline(json_ld_body)
        if text:
            scores["json_ld_article_body"] = _extraction_quality_score(
                text,
                accepted_block_count=max(1, len(text.split("\n\n"))),
                rejected_block_count=0,
                json_ld_article_detected=True,
            )
    if hydration_text:
        scores["hydration_json_body"] = _extraction_quality_score(
            hydration_text,
            accepted_block_count=max(1, len(hydration_text.split("\n\n"))),
            rejected_block_count=0,
            json_ld_article_detected=False,
        )
    if paragraph_result.text:
        scores["visible_text_blocks"] = _extraction_quality_score(
            paragraph_result.text,
            accepted_block_count=paragraph_result.accepted_block_count,
            rejected_block_count=paragraph_result.rejected_block_count,
            json_ld_article_detected=json_ld_article_detected,
        )
    if optional_result is not None:
        scores[optional_result.method] = _extraction_quality_score(
            optional_result.text,
            accepted_block_count=max(1, len(optional_result.text.split("\n\n"))),
            rejected_block_count=0,
            json_ld_article_detected=False,
        )
    return {key: round(value, 4) for key, value in scores.items()}


def _effective_policy(url: str, profile: ExtractionProfile | None) -> _ExtractionPolicy | None:
    built_in = _policy_for_url(url)
    if profile is None:
        return built_in
    return _ExtractionPolicy(
        name=f"{built_in.name}+{profile.name}" if built_in is not None else profile.name,
        domain_suffixes=built_in.domain_suffixes if built_in is not None else (),
        low_value_phrases=(built_in.low_value_phrases if built_in else ()) + profile.low_value_phrases,
        skip_attribute_tokens=(
            (built_in.skip_attribute_tokens if built_in else frozenset())
            | profile.skip_attribute_tokens
        ),
        skip_attribute_phrases=(
            (built_in.skip_attribute_phrases if built_in else ()) + profile.skip_attribute_phrases
        ),
        paywall_or_partial_phrases=(
            (built_in.paywall_or_partial_phrases if built_in else ())
            + profile.paywall_or_partial_phrases
        ),
    )


def _iter_json_ld_objects(scripts: Iterable[str]) -> Iterable[dict[str, Any]]:
    emitted = 0
    for script in scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(payload):
            yield item
            emitted += 1
            if emitted >= 5_000:
                return


def _walk_json_ld(value: object, *, depth: int = 0) -> Iterable[dict[str, Any]]:
    if depth > 12:
        return
    if isinstance(value, list):
        for item in value[:500]:
            yield from _walk_json_ld(item, depth=depth + 1)
        return
    if not isinstance(value, dict):
        return
    yield value
    for child in value.values():
        if isinstance(child, dict | list):
            yield from _walk_json_ld(child, depth=depth + 1)


def _select_article_json_ld(
    objects: Iterable[Mapping[str, Any]], *, page_urls: tuple[str, ...], page_title: str | None,
) -> Mapping[str, Any] | None:
    candidates: list[Mapping[str, Any]] = []
    for item in objects:
        types = item.get("@type")
        if isinstance(types, str):
            normalized_types = {types.lower().rstrip("/").rsplit("/", 1)[-1]}
        elif isinstance(types, list):
            normalized_types = {
                str(type_name).lower().rstrip("/").rsplit("/", 1)[-1] for type_name in types
            }
        else:
            normalized_types = set()
        if normalized_types & _ARTICLE_TYPES:
            candidates.append(item)
    return _select_page_article(candidates, page_urls=page_urls, page_title=page_title)


def _page_identity(url: str, base_url: str) -> tuple[str, str, tuple[tuple[str, str], ...]] | None:
    try:
        parsed = urlsplit(urljoin(base_url, url))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    query = tuple(sorted((key, value) for key, value in parse_qsl(parsed.query)
                         if not key.casefold().startswith("utm_")
                         and key.casefold() not in {"fbclid", "gclid", "traffic_source"}))
    return (parsed.hostname.casefold().removeprefix("www."),
            unquote(parsed.path).rstrip("/") or "/", query)


def _article_urls(item: Mapping[str, Any]) -> Iterable[str]:
    for key, value in item.items():
        if _normalized_key(key) not in {"url", "canonicalurl", "mainentityofpage", "id"}:
            continue
        if isinstance(value, Mapping):
            value = value.get("@id") or value.get("url")
        if isinstance(value, str) and (
            value.startswith(("http://", "https://", "/", "#"))
        ):
            yield value


def _select_page_article(
    candidates: list[Mapping[str, Any]], *, page_urls: tuple[str, ...], page_title: str | None,
) -> Mapping[str, Any] | None:
    """Choose the current article, never a longer related report on the same page."""
    targets = {_page_identity(url, page_urls[0]) for url in page_urls}
    title_terms = set(re.findall(r"\w+", (page_title or "").casefold()))
    scored: list[tuple[int, Mapping[str, Any]]] = []
    for item in candidates:
        urls = {_page_identity(url, page_urls[0]) for url in _article_urls(item)} - {None}
        title = _hydration_scalar(item, "headline", "title") or ""
        terms = set(re.findall(r"\w+", title.casefold()))
        if urls & targets:
            score = 3
            # Live-blog entries can all point at the same canonical page.
            # Prefer the page headline to a longer embedded entry or FAQ.
            if title_terms and terms:
                overlap = len(title_terms & terms)
                if terms == title_terms:
                    score += 2
                elif overlap >= 3 and overlap / max(1, min(len(terms), len(title_terms))) >= 0.8:
                    score += 1
                elif min(len(title_terms), len(terms)) >= 4 and overlap == 0:
                    continue
        elif urls:
            # An explicit URL for another story outweighs headline similarity.
            continue
        elif title_terms and terms:
            overlap = len(title_terms & terms)
            if terms == title_terms:
                score = 2
            elif overlap >= 3 and overlap / max(1, min(len(terms), len(title_terms))) >= 0.8:
                score = 1
            else:
                continue
        else:
            score = 0
        scored.append((score, item))
    if not scored:
        return None
    best_score = max(score for score, _ in scored)
    best = [item for score, item in scored if score == best_score]
    # With no identifying evidence, choosing the longest of several articles is
    # unsafe. Metadata/text fallback is preferable to importing a related story.
    if len(best) > 1 and best_score == 0:
        return None
    if len(best) > 1 and best_score < 3:
        identities = {(_hydration_scalar(item, "headline", "title"),
                       _hydration_scalar(item, "datePublished", "publishedAt"),
                       _string_value(item.get("articleBody")) or _hydration_body(item))
                      for item in best}
        if len(identities) > 1:
            return None
    return max(best, key=lambda item: len(_string_value(item.get("articleBody")) or "")
               + len(_hydration_body(item) or ""))


def _string_value(value: object) -> str | None:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, int | float):
        return str(value)
    return None


def _author_value(value: object) -> str | None:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, Mapping):
        return _string_value(value.get("name"))
    if isinstance(value, list):
        authors = [_author_value(item) for item in value]
        joined = ", ".join(author for author in authors if author)
        return joined or None
    return None


def _extract_paragraph_text(
    blocks: Iterable[str],
    *,
    policy: _ExtractionPolicy | None,
) -> _ParagraphExtractionResult:
    accepted: list[str] = []
    seen: set[str] = set()
    rejected = 0
    rejected_boilerplate = 0
    rejected_short = 0
    for block in blocks:
        text = _normalize_text(block)
        lowered = text.lower()
        if not text or lowered in seen:
            rejected += 1
            continue
        if _contains_any_phrase(text, _low_value_phrases(policy)):
            rejected += 1
            rejected_boilerplate += 1
            continue
        if len(text) < 40 and not text.endswith((".", "!", "?", '"', "'")):
            rejected += 1
            rejected_short += 1
            continue
        accepted.append(text)
        seen.add(lowered)
    return _ParagraphExtractionResult(
        text="\n\n".join(accepted),
        accepted_block_count=len(accepted),
        rejected_block_count=rejected,
        rejected_boilerplate_count=rejected_boilerplate,
        rejected_short_count=rejected_short,
    )


def _should_skip_by_attributes(
    tag_name: str,
    attr_map: Mapping[str, str],
    *,
    policy: _ExtractionPolicy | None,
) -> bool:
    if tag_name in {"article", "main", "body", "html"}:
        return False

    relevant_values: list[str] = []
    for key, value in attr_map.items():
        if key in {
            "aria-label",
            "class",
            "data-component",
            "data-testid",
            "data-type",
            "id",
            "role",
        }:
            relevant_values.append(value)
    if not relevant_values:
        return False

    joined = " ".join(relevant_values).lower()
    tokens = set(_ATTRIBUTE_TOKEN_PATTERN.findall(joined.replace("-", " ")))
    if tokens & _skip_attribute_tokens(policy):
        return True
    return any(phrase in joined for phrase in _skip_attribute_phrases(policy))


def _contains_any_phrase(value: str, phrases: Iterable[str]) -> bool:
    lowered = value.lower()
    return any(phrase in lowered for phrase in phrases)


def _matching_phrases(value: str, phrases: Iterable[str]) -> tuple[str, ...]:
    lowered = value.lower()
    return tuple(phrase for phrase in phrases if phrase in lowered)


def _policy_for_url(url: str) -> _ExtractionPolicy | None:
    hostname = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for policy in _PUBLISHER_POLICIES:
        if any(
            hostname == suffix.removeprefix("www.")
            or hostname.endswith(f".{suffix.removeprefix('www.')}")
            for suffix in policy.domain_suffixes
        ):
            return policy
    return None


def _low_value_phrases(policy: _ExtractionPolicy | None) -> tuple[str, ...]:
    return _LOW_VALUE_PHRASES + (policy.low_value_phrases if policy else ())


def _paywall_or_partial_phrases(policy: _ExtractionPolicy | None) -> tuple[str, ...]:
    return _PAYWALL_OR_ACCOUNT_PHRASES + (
        policy.paywall_or_partial_phrases if policy else ()
    )


def _skip_attribute_tokens(policy: _ExtractionPolicy | None) -> set[str]:
    if policy is None:
        return _SKIP_ATTRIBUTE_TOKENS
    return _SKIP_ATTRIBUTE_TOKENS | policy.skip_attribute_tokens


def _skip_attribute_phrases(policy: _ExtractionPolicy | None) -> tuple[str, ...]:
    return _SKIP_ATTRIBUTE_PHRASES + (policy.skip_attribute_phrases if policy else ())


def _extract_with_trafilatura(
    decoded_html: str,
    *,
    base_url: str,
    policy: _ExtractionPolicy | None,
) -> _OptionalExtractorResult | None:
    try:
        trafilatura = import_module("trafilatura")
    except ImportError:
        return None
    extract = getattr(trafilatura, "extract", None)
    if not callable(extract):
        return None
    try:
        extracted = extract(
            decoded_html,
            url=base_url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception:
        return None
    if not isinstance(extracted, str):
        return None
    raw_text = _normalize_multiline(extracted)
    if len(raw_text.split()) < 50:
        return None
    sanitized = _extract_paragraph_text(
        raw_text.split("\n\n"),
        policy=policy,
    )
    text = sanitized.text
    if len(text.split()) < 50:
        return None
    return _OptionalExtractorResult(
        text=text,
        method="trafilatura_fallback",
        metadata={
            "word_count": len(text.split()),
            "raw_word_count": len(raw_text.split()),
            "rejected_block_count": sanitized.rejected_block_count,
            "rejected_boilerplate_count": sanitized.rejected_boilerplate_count,
            "rejected_short_count": sanitized.rejected_short_count,
            "available": True,
        },
    )


def _should_use_optional_extraction(
    *,
    current_text: str,
    current_quality_score: float,
    optional_text: str,
) -> bool:
    current_word_count = len(current_text.split())
    optional_word_count = len(optional_text.split())
    if current_word_count == 0:
        return True
    if current_quality_score < 0.55 and optional_word_count >= current_word_count:
        return True
    return optional_word_count >= round(current_word_count * 1.35)


def _looks_partial_or_paywalled(
    *,
    word_count: int,
    raw_indicators: tuple[str, ...],
    text_indicators: tuple[str, ...],
) -> bool:
    if text_indicators:
        return True
    # A generic site footer saying "Subscribe now" is common on fully accessible
    # short releases. It is not, by itself, evidence that the article is truncated.
    strong_indicators = [indicator for indicator in raw_indicators if indicator != "subscribe now"]
    return bool(strong_indicators) and word_count < 300


def _extraction_quality_score(
    text_content: str,
    *,
    accepted_block_count: int,
    rejected_block_count: int,
    json_ld_article_detected: bool,
) -> float:
    word_count = len(text_content.split())
    if word_count == 0:
        return 0.0

    score = 0.0
    score += min(0.35, word_count / 1_000)
    score += min(0.25, accepted_block_count / 10)
    if json_ld_article_detected:
        score += 0.15

    total_blocks = accepted_block_count + rejected_block_count
    if total_blocks:
        score += 0.25 * (accepted_block_count / total_blocks)
    else:
        score += 0.10

    return round(max(0.0, min(1.0, score)), 4)
