from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

ENTITY_RESOLUTION_VERSION = "deterministic-entity-resolution-v1"
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)
_CORPORATE_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "company", "co", "ltd", "limited",
    "llc", "plc", "pvt", "private", "the",
}


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    GOVERNMENT_BODY = "government_body"
    COMPANY = "company"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    text: str
    entity_type: EntityType = EntityType.OTHER
    country_code: str | None = None
    external_ids: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalEntityRecord:
    entity_key: str
    canonical_name: str
    entity_type: EntityType
    aliases: tuple[str, ...] = ()
    country_code: str | None = None
    external_ids: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class EntityResolution:
    resolver_version: str
    matched_entity_key: str | None
    confidence: float
    match_basis: str
    normalized_candidate: str
    ambiguous: bool


def canonical_entity_key(
    name: str,
    *,
    entity_type: EntityType = EntityType.OTHER,
    country_code: str | None = None,
) -> str:
    material = f"{entity_type.value}|{country_code or ''}|{normalize_entity_name(name, entity_type=entity_type)}"
    return sha256(material.encode("utf-8")).hexdigest()[:32]


def normalize_entity_name(name: str, *, entity_type: EntityType = EntityType.OTHER) -> str:
    normalized = unicodedata.normalize("NFKC", name).casefold()
    normalized = " ".join(_TOKEN_PATTERN.findall(normalized))
    tokens = normalized.split()
    if entity_type in {EntityType.ORGANIZATION, EntityType.COMPANY}:
        while tokens and tokens[-1] in _CORPORATE_SUFFIXES:
            tokens.pop()
    return " ".join(tokens)


def resolve_entity(
    candidate: EntityCandidate,
    records: tuple[CanonicalEntityRecord, ...],
) -> EntityResolution:
    normalized = normalize_entity_name(candidate.text, entity_type=candidate.entity_type)
    if not normalized:
        return EntityResolution(
            resolver_version=ENTITY_RESOLUTION_VERSION,
            matched_entity_key=None,
            confidence=0.0,
            match_basis="empty_candidate",
            normalized_candidate=normalized,
            ambiguous=False,
        )

    external_map = dict(candidate.external_ids)
    scored: list[tuple[float, str, CanonicalEntityRecord]] = []
    for record in records:
        if record.entity_type != candidate.entity_type and candidate.entity_type is not EntityType.OTHER:
            continue
        if candidate.country_code and record.country_code and candidate.country_code != record.country_code:
            continue
        record_external = dict(record.external_ids)
        shared_ids = {
            key for key, value in external_map.items() if value and record_external.get(key) == value
        }
        if shared_ids:
            scored.append((1.0, "external_id", record))
            continue
        names = (record.canonical_name, *record.aliases)
        best = max(
            (_name_similarity(normalized, normalize_entity_name(value, entity_type=record.entity_type)) for value in names),
            default=0.0,
        )
        if best >= 0.72:
            basis = "exact_or_alias" if best == 1.0 else "name_similarity"
            scored.append((best, basis, record))

    if not scored:
        return EntityResolution(
            resolver_version=ENTITY_RESOLUTION_VERSION,
            matched_entity_key=None,
            confidence=0.0,
            match_basis="no_match",
            normalized_candidate=normalized,
            ambiguous=False,
        )
    scored.sort(key=lambda item: (-item[0], item[2].entity_key))
    best_score, basis, best_record = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    ambiguous = second_score >= best_score - 0.05 and scored[1][2].entity_key != best_record.entity_key
    if ambiguous:
        return EntityResolution(
            resolver_version=ENTITY_RESOLUTION_VERSION,
            matched_entity_key=None,
            confidence=round(best_score, 4),
            match_basis="ambiguous",
            normalized_candidate=normalized,
            ambiguous=True,
        )
    return EntityResolution(
        resolver_version=ENTITY_RESOLUTION_VERSION,
        matched_entity_key=best_record.entity_key,
        confidence=round(best_score, 4),
        match_basis=basis,
        normalized_candidate=normalized,
        ambiguous=False,
    )


def _name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    union = left_tokens | right_tokens
    token_jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    prefix = 1.0 if left.startswith(right) or right.startswith(left) else 0.0
    compact_left = left.replace(" ", "")
    compact_right = right.replace(" ", "")
    compact = 1.0 if compact_left == compact_right else 0.0
    return min(1.0, 0.75 * token_jaccard + 0.15 * prefix + 0.10 * compact)
