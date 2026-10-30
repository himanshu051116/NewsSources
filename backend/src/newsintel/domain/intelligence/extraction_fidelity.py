from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from dateutil import parser as date_parser

from newsintel.adapters.extractors.article_html import ExtractedArticle
from newsintel.domain.acquisition.canonicalization import canonicalize_url

_WORD_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True, slots=True)
class ExtractionFidelityReport:
    score: float | None
    label: str
    available_checks: int
    checks: dict[str, float | None]
    discrepancies: tuple[str, ...]
    scope: str = "publisher_page_extraction_fidelity_not_factual_truth"

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "label": self.label,
            "available_checks": self.available_checks,
            "checks": self.checks,
            "discrepancies": list(self.discrepancies),
            "scope": self.scope,
        }


class _MetadataParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.meta: dict[str, list[str]] = {}
        self.canonical_urls: list[str] = []
        self.json_ld_scripts: list[str] = []
        self._in_title = False
        self._capture_json_ld = False
        self._json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): (value or "").strip() for key, value in attrs}
        tag = tag.casefold()
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (values.get("property") or values.get("name") or "").casefold()
            content = values.get("content")
            if key and content:
                self.meta.setdefault(key, []).append(content)
        elif tag == "link":
            rel = {item.casefold() for item in values.get("rel", "").split()}
            href = values.get("href")
            if href and "canonical" in rel:
                self.canonical_urls.append(urljoin(self.base_url, href))
        elif tag == "script" and "ld+json" in values.get("type", "").casefold():
            self._capture_json_ld = True
            self._json_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_json_ld:
            self._json_parts.append(data)
        elif self._in_title:
            self.title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._capture_json_ld:
            payload = "".join(self._json_parts).strip()
            if payload:
                self.json_ld_scripts.append(payload)
            self._capture_json_ld = False
            self._json_parts = []


def assess_extraction_fidelity(
    html: bytes,
    *,
    base_url: str,
    article: ExtractedArticle,
) -> ExtractionFidelityReport:
    """Compare extracted fields with independent signals still present in raw HTML.

    This estimates whether the extractor faithfully reproduced what the publisher
    page exposed.  It does not estimate whether the publisher's reporting is true.
    Missing publisher metadata is not counted as a failure; only available signals
    participate in the score.
    """
    parser = _MetadataParser(base_url)
    parser.feed(_decode(html))
    parser.close()

    titles = _unique_nonempty(
        [
            *parser.meta.get("og:title", []),
            *parser.meta.get("twitter:title", []),
            " ".join(parser.title_parts),
            *_json_ld_values(parser.json_ld_scripts, "headline"),
        ]
    )
    canonical_urls = _unique_nonempty(
        [*parser.canonical_urls, *parser.meta.get("og:url", []), *_json_ld_urls(parser.json_ld_scripts)]
    )
    published_values = _unique_nonempty(
        [
            *parser.meta.get("article:published_time", []),
            *parser.meta.get("date", []),
            *_json_ld_values(parser.json_ld_scripts, "datePublished"),
        ]
    )
    structured_bodies = _unique_nonempty(_json_ld_values(parser.json_ld_scripts, "articleBody"))

    checks: dict[str, float | None] = {
        "title_consistency": None,
        "canonical_consistency": None,
        "publication_time_consistency": None,
        "structured_body_coverage": None,
        "structured_numeric_retention": None,
    }
    discrepancies: list[str] = []
    weighted: list[tuple[float, float]] = []

    if titles:
        value = max(_token_similarity(article.title or "", candidate) for candidate in titles)
        checks["title_consistency"] = round(value, 6)
        weighted.append((value, 0.25))
        if value < 0.75:
            discrepancies.append("headline_differs_from_publisher_metadata")

    if canonical_urls:
        actual = _normalized_url(article.canonical_url or base_url)
        expected = {_normalized_url(value) for value in canonical_urls}
        value = 1.0 if actual in expected else 0.0
        checks["canonical_consistency"] = value
        weighted.append((value, 0.15))
        if value < 1.0:
            discrepancies.append("canonical_url_differs_from_publisher_metadata")

    published = [_parse_datetime(value) for value in published_values]
    published = [value for value in published if value is not None]
    if published and article.published_at is not None:
        actual = _as_utc(article.published_at)
        closest_seconds = min(abs((actual - value).total_seconds()) for value in published)
        value = 1.0 if closest_seconds <= 60 else max(0.0, 1.0 - closest_seconds / 86_400)
        checks["publication_time_consistency"] = round(value, 6)
        weighted.append((value, 0.20))
        if closest_seconds > 300:
            discrepancies.append("publication_time_differs_from_publisher_metadata")

    if structured_bodies:
        reference = max(structured_bodies, key=lambda value: len(_tokens(value)))
        reference_tokens = _tokens(reference)
        extracted_tokens = _tokens(article.text_content)
        value = _containment(reference_tokens, extracted_tokens)
        checks["structured_body_coverage"] = round(value, 6)
        weighted.append((value, 0.30))
        if value < 0.70:
            discrepancies.append("extracted_body_has_low_structured_body_coverage")

        reference_numbers = _numeric_tokens(reference_tokens)
        if reference_numbers:
            extracted_numbers = _numeric_tokens(extracted_tokens)
            numeric_value = len(reference_numbers & extracted_numbers) / len(reference_numbers)
            checks["structured_numeric_retention"] = round(numeric_value, 6)
            weighted.append((numeric_value, 0.10))
            if numeric_value < 1.0:
                discrepancies.append("one_or_more_structured_numeric_facts_missing")

    if not weighted:
        return ExtractionFidelityReport(
            score=None,
            label="unmeasured",
            available_checks=0,
            checks=checks,
            discrepancies=tuple(discrepancies),
        )

    denominator = sum(weight for _value, weight in weighted)
    score = sum(value * weight for value, weight in weighted) / denominator
    label = "strong" if score >= 0.90 else "moderate" if score >= 0.75 else "weak"
    return ExtractionFidelityReport(
        score=round(score, 6),
        label=label,
        available_checks=len(weighted),
        checks=checks,
        discrepancies=tuple(dict.fromkeys(discrepancies)),
    )


def _json_ld_values(scripts: list[str], key: str) -> list[str]:
    values: list[str] = []
    for script in scripts:
        try:
            payload: Any = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in _walk_json(payload):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return values


def _json_ld_urls(scripts: list[str]) -> list[str]:
    return _json_ld_values(scripts, "url")


def _walk_json(value: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            output.extend(_walk_json(item))
    elif isinstance(value, dict):
        output.append(value)
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                output.extend(_walk_json(item))
    return output


def _decode(payload: bytes) -> str:
    for encoding in ("utf-8", "windows-1252", "iso-8859-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _tokens(value: str) -> frozenset[str]:
    return frozenset(match.group(0).casefold() for match in _WORD_RE.finditer(value))


def _numeric_tokens(tokens: frozenset[str]) -> frozenset[str]:
    return frozenset(token for token in tokens if any(char.isdigit() for char in token))


def _containment(reference: frozenset[str], extracted: frozenset[str]) -> float:
    if not reference:
        return 0.0
    return len(reference & extracted) / len(reference)


def _token_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _normalized_url(value: str) -> str:
    try:
        return canonicalize_url(value).normalized
    except ValueError:
        return value.strip()


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = date_parser.parse(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _unique_nonempty(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))
