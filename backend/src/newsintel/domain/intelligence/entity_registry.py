from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

ENTITY_REGISTRY_LINK_VERSION = "entity-registry-linker-v1"


class EntityLinkState(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class EntityDescriptor:
    name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    country: str | None = None


@dataclass(frozen=True, slots=True)
class RegistryCandidate:
    external_id: str
    label: str
    entity_type: str | None = None
    aliases: tuple[str, ...] = ()
    country: str | None = None
    canonical_url: str | None = None


@dataclass(frozen=True, slots=True)
class ScoredRegistryCandidate:
    external_id: str
    label: str
    score: float
    canonical_url: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EntityRegistryResolution:
    methodology_version: str
    state: EntityLinkState
    selected: ScoredRegistryCandidate | None
    candidates: tuple[ScoredRegistryCandidate, ...]
    interpretation: str


def resolve_registry_candidates(
    entity: EntityDescriptor,
    candidates: tuple[RegistryCandidate, ...],
    *,
    threshold: float = 0.82,
    ambiguity_margin: float = 0.08,
) -> EntityRegistryResolution:
    scored = tuple(
        sorted(
            (_score(entity, item) for item in candidates),
            key=lambda item: (-item.score, item.external_id),
        )
    )
    selected = scored[0] if scored else None
    if selected is None or selected.score < threshold:
        state = EntityLinkState.NO_MATCH
        selected = None
    elif len(scored) > 1 and selected.score - scored[1].score < ambiguity_margin:
        state = EntityLinkState.AMBIGUOUS
        selected = None
    else:
        state = EntityLinkState.MATCHED
    return EntityRegistryResolution(
        methodology_version=ENTITY_REGISTRY_LINK_VERSION,
        state=state,
        selected=selected,
        candidates=scored[:10],
        interpretation=(
            "Registry linking uses identity attributes only. A resolved external identifier improves entity identity consistency and does not validate factual claims about the entity."
        ),
    )


def _score(entity: EntityDescriptor, candidate: RegistryCandidate) -> ScoredRegistryCandidate:
    target_names = {_norm(entity.name), *(_norm(item) for item in entity.aliases)}
    candidate_names = {_norm(candidate.label), *(_norm(item) for item in candidate.aliases)}
    target_names.discard("")
    candidate_names.discard("")
    reasons: list[str] = []
    exact = bool(target_names & candidate_names)
    name_score = 1.0 if exact else max(
        (_token_jaccard(left, right) for left in target_names for right in candidate_names),
        default=0.0,
    )
    if exact:
        reasons.append("exact normalized name/alias")
    elif name_score >= 0.7:
        reasons.append("strong token similarity")
    score = 0.72 * name_score
    if candidate.entity_type:
        if _norm(candidate.entity_type) == _norm(entity.entity_type):
            score += 0.18
            reasons.append("entity-type match")
        else:
            score -= 0.2
            reasons.append("entity-type mismatch")
    if entity.country and candidate.country:
        if _norm(entity.country) == _norm(candidate.country):
            score += 0.1
            reasons.append("country match")
        else:
            score -= 0.12
            reasons.append("country mismatch")
    return ScoredRegistryCandidate(
        external_id=candidate.external_id,
        label=candidate.label,
        score=round(max(0.0, min(1.0, score)), 6),
        canonical_url=candidate.canonical_url,
        reasons=tuple(reasons),
    )


def _norm(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _token_jaccard(left: str, right: str) -> float:
    a = set(left.split())
    b = set(right.split())
    return len(a & b) / len(a | b) if a and b else 0.0
