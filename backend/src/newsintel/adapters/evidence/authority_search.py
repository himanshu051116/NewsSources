from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote_plus, urljoin, urlsplit

from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult
from newsintel.adapters.evidence.specialized import (
    ckan_candidate_urls,
    configured_json_candidate_urls,
    socrata_candidate_urls,
)
from newsintel.domain.intelligence.authority import authority_matches_source, normalize_domains

AUTHORITY_SEARCH_ADAPTER_VERSION = "authority-search-adapter-v2"


class AuthorityAdapterType(StrEnum):
    GENERIC_HTML_SEARCH = "generic_html_search"
    DIRECT_DOCUMENT_TEMPLATE = "direct_document_template"
    GENERIC_JSON_SEARCH = "generic_json_search"
    CKAN_PACKAGE_SEARCH = "ckan_package_search"
    SOCRATA_CATALOG_SEARCH = "socrata_catalog_search"


@dataclass(frozen=True, slots=True)
class AuthoritySearchSpec:
    authority_id: str
    name: str
    evidence_class: str
    base_url: str
    allowed_domains: tuple[str, ...]
    search_url_template: str | None
    adapter_type: AuthorityAdapterType = AuthorityAdapterType.GENERIC_HTML_SEARCH
    adapter_config: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.allowed_domains:
            raise ValueError("authority search requires at least one allowed domain")
        normalized = tuple(normalize_domains(list(self.allowed_domains)))
        if not normalized:
            raise ValueError("authority search requires valid allowed domains")
        object.__setattr__(self, "allowed_domains", normalized)
        if self.search_url_template:
            _validate_template(self.search_url_template)
            rendered = render_search_url(self.search_url_template, "validation")
            if not authority_matches_source(
                source_url=rendered,
                allowed_domains=list(normalized),
            ):
                raise ValueError("authority search template must remain inside allowed domains")
        if self.adapter_type is AuthorityAdapterType.GENERIC_JSON_SEARCH:
            raw_fields = self.adapter_config.get("candidate_fields")
            if not isinstance(raw_fields, list) or not any(
                isinstance(item, str) and item.strip() for item in raw_fields
            ):
                raise ValueError(
                    "generic_json_search requires adapter_config.candidate_fields"
                )


@dataclass(frozen=True, slots=True)
class RetrievedEvidenceDocument:
    authority_id: str
    evidence_class: str
    source_url: str
    final_url: str
    content_type: str | None
    body_sha256: str
    text: str
    retrieved_at_iso: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class EvidenceRetrievalAttempt:
    authority_id: str
    search_url: str | None
    candidate_url: str | None
    status: str
    http_status: int | None
    body_sha256: str | None
    error_type: str | None
    error_message: str | None
    metadata: dict[str, object]


class _FetcherProtocol:
    async def fetch(self, request: FetchRequest) -> FetchResult:  # pragma: no cover - protocol shape
        raise NotImplementedError


class AuthoritySearchExecutor:
    """Execute administrator-approved authority searches under a bounded fetch policy.

    The executor never follows or emits evidence URLs outside the authority's configured
    domain allow-list. Search templates accept only the ``{query}`` placeholder.
    """

    def __init__(self, fetcher: _FetcherProtocol) -> None:
        self._fetcher = fetcher

    async def retrieve(
        self,
        spec: AuthoritySearchSpec,
        *,
        query: str,
        max_candidates: int = 3,
        max_document_chars: int = 250_000,
    ) -> tuple[list[RetrievedEvidenceDocument], list[EvidenceRetrievalAttempt]]:
        if max_candidates < 1 or max_candidates > 20:
            raise ValueError("max_candidates must be between 1 and 20")
        if max_document_chars < 1_000 or max_document_chars > 1_000_000:
            raise ValueError("max_document_chars outside allowed range")
        template = spec.search_url_template
        if not template:
            return [], [
                EvidenceRetrievalAttempt(
                    authority_id=spec.authority_id,
                    search_url=None,
                    candidate_url=None,
                    status="skipped_no_search_template",
                    http_status=None,
                    body_sha256=None,
                    error_type=None,
                    error_message=None,
                    metadata={"adapter_version": AUTHORITY_SEARCH_ADAPTER_VERSION},
                )
            ]

        search_url = render_search_url(template, query)
        _assert_allowed(search_url, spec.allowed_domains)
        attempts: list[EvidenceRetrievalAttempt] = []
        try:
            search_result = await self._fetcher.fetch(FetchRequest(url=search_url, allowed_domains=spec.allowed_domains))
        except Exception as exc:  # bounded transport errors are recorded rather than hidden
            attempts.append(
                EvidenceRetrievalAttempt(
                    authority_id=spec.authority_id,
                    search_url=search_url,
                    candidate_url=None,
                    status="search_error",
                    http_status=None,
                    body_sha256=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:1000],
                    metadata={"adapter_version": AUTHORITY_SEARCH_ADAPTER_VERSION},
                )
            )
            return [], attempts

        attempts.append(
            EvidenceRetrievalAttempt(
                authority_id=spec.authority_id,
                search_url=search_url,
                candidate_url=None,
                status="search_fetched",
                http_status=search_result.status_code,
                body_sha256=search_result.body_sha256,
                error_type=None,
                error_message=None,
                metadata={
                    "adapter_version": AUTHORITY_SEARCH_ADAPTER_VERSION,
                    "final_url": search_result.final_url,
                    "content_type": _content_type(search_result),
                },
            )
        )
        if not (200 <= search_result.status_code < 300):
            return [], attempts

        if spec.adapter_type is AuthorityAdapterType.DIRECT_DOCUMENT_TEMPLATE:
            candidate_urls = [search_result.final_url]
        elif spec.adapter_type is AuthorityAdapterType.CKAN_PACKAGE_SEARCH:
            candidate_urls = ckan_candidate_urls(
                search_result.body,
                base_url=spec.base_url,
                max_results=max_candidates,
            )
        elif spec.adapter_type is AuthorityAdapterType.SOCRATA_CATALOG_SEARCH:
            candidate_urls = socrata_candidate_urls(
                search_result.body,
                max_results=max_candidates,
            )
        elif spec.adapter_type is AuthorityAdapterType.GENERIC_JSON_SEARCH:
            raw_fields = spec.adapter_config.get("candidate_fields")
            fields = tuple(str(item) for item in raw_fields) if isinstance(raw_fields, list) else ()
            candidate_urls = configured_json_candidate_urls(
                search_result.body,
                base_url=search_result.final_url,
                candidate_fields=fields,
                max_results=max_candidates,
            )
        else:
            candidate_urls = discover_candidate_urls(
                search_result,
                allowed_domains=spec.allowed_domains,
                max_results=max_candidates,
            )
            # A search endpoint can itself be an evidence document. Use it only when no
            # links were found, to avoid silently discarding a direct authority response.
            if not candidate_urls and _looks_like_document(search_result):
                candidate_urls = [search_result.final_url]

        documents: list[RetrievedEvidenceDocument] = []
        seen: set[str] = set()
        for candidate_url in candidate_urls[:max_candidates]:
            _assert_allowed(candidate_url, spec.allowed_domains)
            normalized = _normalized_url(candidate_url)
            if normalized in seen:
                continue
            seen.add(normalized)
            if normalized == _normalized_url(search_result.final_url):
                candidate_result = search_result
            else:
                try:
                    candidate_result = await self._fetcher.fetch(FetchRequest(url=candidate_url, allowed_domains=spec.allowed_domains))
                except Exception as exc:
                    attempts.append(
                        EvidenceRetrievalAttempt(
                            authority_id=spec.authority_id,
                            search_url=search_url,
                            candidate_url=candidate_url,
                            status="candidate_error",
                            http_status=None,
                            body_sha256=None,
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:1000],
                            metadata={"adapter_version": AUTHORITY_SEARCH_ADAPTER_VERSION},
                        )
                    )
                    continue
            attempts.append(
                EvidenceRetrievalAttempt(
                    authority_id=spec.authority_id,
                    search_url=search_url,
                    candidate_url=candidate_url,
                    status="candidate_fetched",
                    http_status=candidate_result.status_code,
                    body_sha256=candidate_result.body_sha256,
                    error_type=None,
                    error_message=None,
                    metadata={
                        "adapter_version": AUTHORITY_SEARCH_ADAPTER_VERSION,
                        "final_url": candidate_result.final_url,
                        "content_type": _content_type(candidate_result),
                    },
                )
            )
            if not (200 <= candidate_result.status_code < 300):
                continue
            if not authority_matches_source(
                source_url=candidate_result.final_url,
                allowed_domains=list(spec.allowed_domains),
            ):
                attempts.append(
                    EvidenceRetrievalAttempt(
                        authority_id=spec.authority_id,
                        search_url=search_url,
                        candidate_url=candidate_url,
                        status="rejected_cross_domain_redirect",
                        http_status=candidate_result.status_code,
                        body_sha256=candidate_result.body_sha256,
                        error_type="AuthorityDomainViolation",
                        error_message="final URL left the configured evidence authority domains",
                        metadata={"final_url": candidate_result.final_url},
                    )
                )
                continue
            text = extract_document_text(candidate_result.body, _content_type(candidate_result))
            text = text[:max_document_chars]
            if len(text.split()) < 8:
                continue
            documents.append(
                RetrievedEvidenceDocument(
                    authority_id=spec.authority_id,
                    evidence_class=spec.evidence_class,
                    source_url=candidate_url,
                    final_url=candidate_result.final_url,
                    content_type=_content_type(candidate_result),
                    body_sha256=candidate_result.body_sha256,
                    text=text,
                    retrieved_at_iso=candidate_result.retrieved_at.isoformat(),
                    metadata={
                        "adapter_version": AUTHORITY_SEARCH_ADAPTER_VERSION,
                        "search_url": search_url,
                        "redirect_chain": list(candidate_result.redirect_chain),
                    },
                )
            )
        return documents, attempts


def render_search_url(template: str, query: str) -> str:
    _validate_template(template)
    return template.replace("{query}", quote_plus(" ".join(query.split())))


def discover_candidate_urls(
    result: FetchResult,
    *,
    allowed_domains: tuple[str, ...],
    max_results: int = 10,
) -> list[str]:
    content_type = _content_type(result)
    if content_type and "json" in content_type:
        raw = _urls_from_json(result.body)
    else:
        parser = _LinkParser()
        parser.feed(result.body.decode("utf-8", errors="replace"))
        raw = [urljoin(result.final_url, href) for href in parser.links]
    candidates: list[str] = []
    for value in raw:
        if len(candidates) >= max_results:
            break
        if not _is_http_url(value):
            continue
        if not authority_matches_source(source_url=value, allowed_domains=list(allowed_domains)):
            continue
        normalized = _normalized_url(value)
        if normalized == _normalized_url(result.final_url):
            continue
        if _looks_like_asset(value):
            continue
        if normalized not in {_normalized_url(item) for item in candidates}:
            candidates.append(value)
    return candidates


def extract_document_text(body: bytes, content_type: str | None) -> str:
    decoded = body.decode("utf-8", errors="replace")
    if content_type and "json" in content_type:
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError:
            return " ".join(decoded.split())
        return _json_text(parsed)
    if content_type and any(
        token in content_type for token in ("text/csv", "application/csv", "tab-separated-values")
    ):
        # Preserve tabular rows as bounded plain text for numeric/statistical evidence checks.
        # This is intentionally not a full dataframe parser; schema-aware processing belongs in
        # a later dataset adapter and must retain the raw artifact separately.
        return " ".join(decoded.replace("\t", " ").replace(",", " ").split())
    if content_type and not any(
        token in content_type for token in ("html", "text/plain", "xml", "xhtml")
    ):
        return ""
    parser = _VisibleTextParser()
    parser.feed(decoded)
    return " ".join(parser.text_parts).strip()


def _validate_template(template: str) -> None:
    placeholders = re.findall(r"\{([^{}]+)\}", template)
    if any(item != "query" for item in placeholders):
        raise ValueError("search_url_template supports only the {query} placeholder")
    if "{query}" not in template:
        raise ValueError("search_url_template must contain {query}")
    rendered = template.replace("{query}", "validation")
    if not _is_http_url(rendered):
        raise ValueError("search_url_template must be an HTTP(S) URL")
    sensitive_names = {"api_key", "apikey", "access_token", "token", "key", "secret"}
    for name, value in parse_qsl(urlsplit(rendered).query, keep_blank_values=True):
        if name.casefold() in sensitive_names and value:
            raise ValueError(
                "search_url_template must not embed API keys, tokens, or secrets in the URL"
            )


def _assert_allowed(url: str, allowed_domains: tuple[str, ...]) -> None:
    if not authority_matches_source(source_url=url, allowed_domains=list(allowed_domains)):
        raise ValueError("evidence URL is outside the configured authority domain allow-list")


def _urls_from_json(body: bytes) -> list[str]:
    try:
        value = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    found: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, str) and _is_http_url(item):
            found.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def _json_text(value: object) -> str:
    parts: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, int | float | bool):
            parts.append(str(item))
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return " ".join(" ".join(parts).split())


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        for key, value in attrs:
            if key.casefold() == "href" and value:
                self.links.append(value.strip())
                return


class _VisibleTextParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        compact = " ".join(data.split())
        if compact:
            self.text_parts.append(compact)


def _content_type(result: FetchResult) -> str | None:
    value = result.headers.get("content-type")
    if not value:
        return None
    return value.split(";", 1)[0].strip().casefold()


def _looks_like_document(result: FetchResult) -> bool:
    content_type = _content_type(result)
    return content_type is None or any(
        token in content_type for token in ("html", "text/plain", "json", "xml", "xhtml")
    )


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _normalized_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    return parsed._replace(fragment="").geturl()


def _looks_like_asset(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return path.endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".svg",
            ".css",
            ".js",
            ".zip",
            ".mp3",
            ".mp4",
            ".webm",
        )
    )
