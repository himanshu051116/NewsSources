from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HISTORICAL_ENRICHMENT_VERSION = "historical-enrichment-v3"

_STOPWORDS = {
    "about", "after", "against", "amid", "among", "and", "are", "before", "but",
    "for", "from", "has", "have", "into", "its", "new", "news", "not", "over",
    "said", "says", "that", "the", "their", "this", "through", "under", "with",
    "will", "would", "today", "latest", "report", "reports",
    "और", "का", "की", "के", "को", "में", "से", "पर", "है", "हैं", "था",
    "थी", "ने", "यह", "वह", "एक", "लिए", "बाद", "तक", "भी",
}


def build_historical_queries(
    *,
    title: str,
    claim_features: Iterable[dict[str, object]],
    max_queries: int = 3,
) -> tuple[str, ...]:
    """Build bounded, deterministic historical queries from article title and claim entities."""

    entities: list[str] = []
    seen_entities: set[str] = set()
    for features in claim_features:
        raw_entities = features.get("entities")
        if not isinstance(raw_entities, list):
            continue
        for value in raw_entities:
            entity = " ".join(str(value).split()).strip(" ,.;:")
            key = entity.casefold()
            if len(entity) < 3 or key in seen_entities:
                continue
            seen_entities.add(key)
            entities.append(entity)

    title_terms: list[str] = []
    seen_terms: set[str] = set()
    for token in _unicode_words(title):
        key = token.casefold()
        if len(token) < 3 or key in _STOPWORDS or key in seen_terms:
            continue
        seen_terms.add(key)
        title_terms.append(token)

    queries: list[str] = []
    if entities:
        queries.append(" ".join(entities[:3]))
    if entities and title_terms:
        queries.append(" ".join([entities[0], *title_terms[:4]]))
    if title_terms:
        queries.append(" ".join(title_terms[:6]))
    if not queries:
        normalized = " ".join(title.split()).strip()
        if normalized:
            queries.append(normalized[:500])

    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = " ".join(query.split()).strip()
        key = normalized.casefold()
        if len(normalized) < 2 or key in seen:
            continue
        seen.add(key)
        unique.append(normalized[:500])
        if len(unique) >= max_queries:
            break
    return tuple(unique)


def _unicode_words(text: str) -> tuple[str, ...]:
    values: list[str] = []
    buffer: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category[:1] in {"L", "N", "M"} or char in {".", "'", "’", "_", "-"}:
            buffer.append(char)
            continue
        if buffer:
            token = "".join(buffer).strip(".'’_-")
            if token:
                values.append(token)
            buffer.clear()
    if buffer:
        token = "".join(buffer).strip(".'’_-")
        if token:
            values.append(token)
    return tuple(values)


def historical_depth(
    *,
    same_event_count: int,
    prior_claim_count: int,
    internal_match_count: int,
    external_match_count: int,
) -> str:
    score = (
        min(same_event_count, 3) * 3
        + min(prior_claim_count, 5) * 2
        + min(internal_match_count, 10)
        + min(external_match_count, 10)
    )
    if score >= 16:
        return "deep"
    if score >= 7:
        return "moderate"
    if score >= 2:
        return "limited"
    return "none"


def timeline_summary(
    observed_times: Iterable[datetime],
    *,
    cutoff_at: datetime,
) -> dict[str, object]:
    values = sorted({value for value in observed_times if value < cutoff_at})
    if not values:
        return {
            "historical_item_count": 0,
            "earliest_at": None,
            "latest_prior_at": None,
            "span_days": 0,
            "cutoff_at": cutoff_at.isoformat(),
        }
    return {
        "historical_item_count": len(values),
        "earliest_at": values[0].isoformat(),
        "latest_prior_at": values[-1].isoformat(),
        "span_days": max(0, (values[-1] - values[0]).days),
        "cutoff_at": cutoff_at.isoformat(),
    }


_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "source",
}


def normalize_history_url(value: object) -> str | None:
    """Return a stable URL identity key without common tracking parameters."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.casefold()
    # Accessing .port can itself raise ValueError for malformed external URLs.
    # Historical discovery must discard such URLs rather than fail an entire job.
    try:
        port = parsed.port
    except ValueError:
        return None
    # Brackets are required when reconstructing a valid IPv6 URL.
    if ":" in host:
        host = f"[{host}]"
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING_QUERY_KEYS
        and not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    return urlunsplit((parsed.scheme.lower(), host, path, urlencode(query_items), ""))


def deduplicate_history_items(
    items: Iterable[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    """Deduplicate article-like history entries while keeping the strongest match."""
    best: dict[str, dict[str, object]] = {}
    order: list[str] = []
    dropped = 0
    for item in items:
        url = item.get("url") or item.get("source_url")
        url_key = normalize_history_url(url)
        version_id = item.get("article_version_id")
        relationship = str(item.get("relationship") or "")
        title = " ".join(str(item.get("title") or "").casefold().split())
        published = str(item.get("published_at") or "")[:10]
        if relationship == "same_article_prior_version" and version_id:
            key = f"version:{version_id}"
        else:
            key = url_key or (
                f"version:{version_id}" if version_id else f"title:{title}:{published}"
            )
        if not key or key == "title::":
            key = f"item:{len(order)}"
        existing = best.get(key)
        if existing is None:
            best[key] = dict(item)
            order.append(key)
            continue
        dropped += 1
        existing_score = _number(existing.get("relevance_score"))
        incoming_score = _number(item.get("relevance_score"))
        if incoming_score > existing_score:
            best[key] = dict(item)
    return [best[key] for key in order], dropped


def historical_relevance_score(
    *,
    same_event: bool = False,
    claim_family_match: bool = False,
    entity_overlap: float = 0.0,
    lexical_overlap: float = 0.0,
    source_signal: float = 0.5,
) -> dict[str, object]:
    """Score contextual linkage strength; this is not a factual-truth score."""
    entity_overlap = _bounded(entity_overlap)
    lexical_overlap = _bounded(lexical_overlap)
    source_signal = _bounded(source_signal)
    score = (
        (0.45 if same_event else 0.0)
        + (0.30 if claim_family_match else 0.0)
        + 0.10 * entity_overlap
        + 0.10 * lexical_overlap
        + 0.05 * source_signal
    )
    score = round(min(1.0, score), 6)
    if score >= 0.75:
        label = "high"
    elif score >= 0.45:
        label = "moderate"
    elif score >= 0.20:
        label = "limited"
    else:
        label = "weak"
    return {
        "score": score,
        "label": label,
        "scope": "historical_linkage_not_factual_truth",
        "signals": {
            "same_event": same_event,
            "claim_family_match": claim_family_match,
            "entity_overlap": round(entity_overlap, 6),
            "lexical_overlap": round(lexical_overlap, 6),
            "source_signal": round(source_signal, 6),
        },
    }


def historical_context_confidence(
    *,
    relevance_scores: Iterable[float],
    source_diversity_count: int,
    channel_count: int,
    duplicate_count: int,
) -> dict[str, object]:
    """Estimate confidence that enough relevant historical context was found."""
    scores = sorted((_bounded(value) for value in relevance_scores), reverse=True)
    top = scores[:5]
    top_mean = sum(top) / len(top) if top else 0.0
    diversity = min(1.0, max(0, source_diversity_count) / 4)
    channels = min(1.0, max(0, channel_count) / 4)
    duplicate_penalty = min(0.20, max(0, duplicate_count) * 0.01)
    score = max(0.0, min(1.0, 0.65 * top_mean + 0.20 * diversity + 0.15 * channels - duplicate_penalty))
    score = round(score, 6)
    if score >= 0.72:
        label = "high"
    elif score >= 0.45:
        label = "moderate"
    elif score > 0:
        label = "limited"
    else:
        label = "none"
    return {
        "score": score,
        "label": label,
        "scope": "historical_context_coverage_not_factual_truth",
        "top_match_mean": round(top_mean, 6),
        "source_diversity_count": max(0, source_diversity_count),
        "channel_count": max(0, channel_count),
        "duplicate_count": max(0, duplicate_count),
    }


def classify_claim_evolution(
    *,
    numeric_changed: bool,
    temporal_changed: bool,
    text_changed: bool,
    same_temporal_reference: bool,
) -> str:
    if numeric_changed and temporal_changed:
        return "temporal_numeric_update"
    if numeric_changed and same_temporal_reference:
        return "numeric_revision_candidate"
    if numeric_changed:
        return "numeric_update"
    if temporal_changed:
        return "temporal_update"
    if text_changed:
        return "wording_update"
    return "unchanged"


def summarize_change_pattern(
    *,
    current_claim_count: int,
    new_claim_count: int,
    recurring_claim_count: int,
    changed_claim_count: int,
    revision_candidate_count: int,
) -> str:
    if current_claim_count <= 0:
        return "no_checkable_claims"
    if recurring_claim_count == 0:
        return "mostly_new_reporting"
    if revision_candidate_count > 0:
        return "possible_conflict_or_revision"
    if changed_claim_count >= max(1, recurring_claim_count // 2):
        return "material_update"
    if new_claim_count > recurring_claim_count:
        return "mostly_new_reporting"
    return "continuity_with_prior_reporting"


def _bounded(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
