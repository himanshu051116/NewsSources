from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from hashlib import sha256

from newsintel.domain.intelligence.claims import (
    claim_family_text,
    extract_quantities,
    extract_temporal_references,
    split_sentences,
)

EVIDENCE_MATCHER_VERSION = "deterministic-evidence-passage-v1"


class EvidencePassageRelationship(StrEnum):
    MATCHING_ASSERTION = "matching_assertion"
    POTENTIAL_NUMERIC_CONFLICT = "potential_numeric_conflict"
    POTENTIAL_TEMPORAL_CONFLICT = "potential_temporal_conflict"
    RELATED_CONTEXT = "related_context"
    LOW_RELEVANCE = "low_relevance"


@dataclass(frozen=True, slots=True)
class EvidencePassage:
    text: str
    sentence_index: int
    passage_sha256: str
    relationship: EvidencePassageRelationship
    similarity_score: float
    lexical_overlap: float
    metadata: dict[str, object]


def find_evidence_passages(
    claim_text: str,
    evidence_text: str,
    *,
    max_passages: int = 5,
    minimum_similarity: float = 0.2,
) -> tuple[EvidencePassage, ...]:
    """Retrieve auditable evidence passages without turning similarity into a truth verdict."""

    candidates: list[EvidencePassage] = []
    for sentence_index, sentence in enumerate(split_sentences(evidence_text)):
        similarity = _similarity(claim_text, sentence)
        lexical = _lexical_overlap(claim_text, sentence)
        if max(similarity, lexical) < minimum_similarity:
            continue
        relationship, metadata = _relationship(claim_text, sentence, similarity, lexical)
        candidates.append(
            EvidencePassage(
                text=sentence,
                sentence_index=sentence_index,
                passage_sha256=sha256(sentence.encode("utf-8")).hexdigest(),
                relationship=relationship,
                similarity_score=round(similarity, 4),
                lexical_overlap=round(lexical, 4),
                metadata=metadata,
            )
        )
    candidates.sort(
        key=lambda item: (
            _relationship_rank(item.relationship),
            item.similarity_score,
            item.lexical_overlap,
        ),
        reverse=True,
    )
    return tuple(candidates[:max_passages])


def _relationship(
    claim_text: str,
    passage: str,
    similarity: float,
    lexical: float,
) -> tuple[EvidencePassageRelationship, dict[str, object]]:
    claim_family = claim_family_text(claim_text)
    passage_family = claim_family_text(passage)
    family_similarity = SequenceMatcher(None, claim_family, passage_family).ratio()
    claim_quantities = extract_quantities(claim_text)
    passage_quantities = extract_quantities(passage)
    claim_temporal = extract_temporal_references(claim_text)
    passage_temporal = extract_temporal_references(passage)

    quantity_conflict = (
        bool(claim_quantities)
        and bool(passage_quantities)
        and _quantity_signature(claim_quantities) != _quantity_signature(passage_quantities)
    )
    temporal_conflict = (
        bool(claim_temporal)
        and bool(passage_temporal)
        and _temporal_signature(claim_temporal) != _temporal_signature(passage_temporal)
    )
    metadata: dict[str, object] = {
        "matcher_version": EVIDENCE_MATCHER_VERSION,
        "claim_family_similarity": round(family_similarity, 4),
        "claim_quantities": list(claim_quantities),
        "passage_quantities": list(passage_quantities),
        "claim_temporal_references": list(claim_temporal),
        "passage_temporal_references": list(passage_temporal),
        "warning": (
            "Textual matching identifies candidate evidence only; it is not a factual verdict."
        ),
    }

    if family_similarity >= 0.72 and quantity_conflict:
        return EvidencePassageRelationship.POTENTIAL_NUMERIC_CONFLICT, metadata
    if family_similarity >= 0.72 and temporal_conflict:
        return EvidencePassageRelationship.POTENTIAL_TEMPORAL_CONFLICT, metadata
    if family_similarity >= 0.72 and (similarity >= 0.65 or lexical >= 0.6):
        return EvidencePassageRelationship.MATCHING_ASSERTION, metadata
    if similarity >= 0.35 or lexical >= 0.35:
        return EvidencePassageRelationship.RELATED_CONTEXT, metadata
    return EvidencePassageRelationship.LOW_RELEVANCE, metadata


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _norm(left), _norm(right), autojunk=False).ratio()


def _lexical_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union else 0.0


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W_][\w\u0300-\u036F\u0900-\u097F]*", text.casefold())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _quantity_signature(values: tuple[dict[str, object], ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            item.get("kind"),
            item.get("normalized_value"),
            item.get("unit"),
            item.get("currency"),
        )
        for item in values
    )


def _temporal_signature(values: tuple[dict[str, object], ...]) -> tuple[tuple[object, ...], ...]:
    return tuple((item.get("kind"), item.get("normalized"), item.get("raw")) for item in values)


def _relationship_rank(value: EvidencePassageRelationship) -> int:
    return {
        EvidencePassageRelationship.POTENTIAL_NUMERIC_CONFLICT: 5,
        EvidencePassageRelationship.POTENTIAL_TEMPORAL_CONFLICT: 5,
        EvidencePassageRelationship.MATCHING_ASSERTION: 4,
        EvidencePassageRelationship.RELATED_CONTEXT: 2,
        EvidencePassageRelationship.LOW_RELEVANCE: 1,
    }[value]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


_STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "was",
    "were",
    "are",
    "has",
    "have",
    "had",
    "said",
    "reported",
}
