from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

KNOWLEDGE_SEARCH_VERSION = "temporal-knowledge-hybrid-search-v1"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.I)


@dataclass(frozen=True, slots=True)
class KnowledgeSearchDocument:
    node_key: str
    node_type: str
    label: str
    observed_at: datetime
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class KnowledgeSearchHit:
    node_key: str
    score: float
    matched_terms: tuple[str, ...]
    match_basis: tuple[str, ...]


def rank_knowledge_nodes(
    query: str,
    documents: tuple[KnowledgeSearchDocument, ...],
    *,
    node_types: tuple[str, ...] = (),
    limit: int = 25,
) -> tuple[KnowledgeSearchHit, ...]:
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    terms = tuple(dict.fromkeys(token.casefold() for token in _TOKEN_PATTERN.findall(query)))
    if not terms:
        return ()
    allowed = set(node_types)
    hits: list[KnowledgeSearchHit] = []
    for document in documents:
        if allowed and document.node_type not in allowed:
            continue
        label_tokens = set(token.casefold() for token in _TOKEN_PATTERN.findall(document.label))
        payload_text = " ".join(_flatten_strings(document.payload))
        payload_tokens = set(token.casefold() for token in _TOKEN_PATTERN.findall(payload_text))
        matched_label = tuple(term for term in terms if term in label_tokens)
        matched_payload = tuple(term for term in terms if term in payload_tokens and term not in matched_label)
        if not matched_label and not matched_payload:
            continue
        coverage = (len(matched_label) + 0.6 * len(matched_payload)) / len(terms)
        exact_phrase = 1.0 if query.casefold().strip() in document.label.casefold() else 0.0
        score = min(1.0, 0.75 * coverage + 0.25 * exact_phrase)
        basis: list[str] = []
        if matched_label:
            basis.append("label")
        if matched_payload:
            basis.append("payload")
        if exact_phrase:
            basis.append("exact_phrase")
        hits.append(
            KnowledgeSearchHit(
                node_key=document.node_key,
                score=round(score, 4),
                matched_terms=tuple(dict.fromkeys((*matched_label, *matched_payload))),
                match_basis=tuple(basis),
            )
        )
    hits.sort(key=lambda item: (-item.score, item.node_key))
    return tuple(hits[:limit])


def search_terms(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(token.casefold() for token in _TOKEN_PATTERN.findall(value)))


def _flatten_strings(value: object) -> list[str]:
    result: list[str] = []
    if isinstance(value, str):
        result.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            result.extend(_flatten_strings(child))
    elif isinstance(value, list | tuple):
        for child in value:
            result.extend(_flatten_strings(child))
    return result
