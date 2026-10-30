from __future__ import annotations

from dataclasses import dataclass

ORCHESTRATION_VERSION = "multi-authority-evidence-orchestration-v1"


@dataclass(frozen=True, slots=True)
class AuthorityOption:
    authority_id: str
    evidence_class: str
    jurisdiction: str = "global"
    language: str | None = None
    authority_domain: str | None = None
    active: bool = True
    prior_success_rate: float | None = None
    prior_attempted: bool = False


@dataclass(frozen=True, slots=True)
class AuthoritySelection:
    authority_id: str
    evidence_class: str
    score: float
    reason: str


@dataclass(frozen=True, slots=True)
class OrchestrationPlan:
    orchestration_version: str
    selections: tuple[AuthoritySelection, ...]
    uncovered_evidence_classes: tuple[str, ...]
    coverage_ratio: float
    interpretation: str


def plan_authority_orchestration(
    required_evidence_classes: tuple[str, ...],
    authorities: tuple[AuthorityOption, ...],
    *,
    jurisdiction: str | None = None,
    language: str | None = None,
    max_authorities: int = 5,
) -> OrchestrationPlan:
    if max_authorities < 1 or max_authorities > 20:
        raise ValueError("max_authorities must be between 1 and 20")
    requirements = tuple(dict.fromkeys(_norm(item) for item in required_evidence_classes if _norm(item)))
    if not requirements:
        return OrchestrationPlan(
            orchestration_version=ORCHESTRATION_VERSION,
            selections=(),
            uncovered_evidence_classes=(),
            coverage_ratio=1.0,
            interpretation="No explicit primary-evidence class requirement was present.",
        )

    selected: list[AuthoritySelection] = []
    selected_ids: set[str] = set()
    selected_domains: set[str] = set()
    covered: set[str] = set()
    candidates = [item for item in authorities if item.active and _norm(item.evidence_class) in requirements]

    # First cover distinct evidence classes. Then use remaining capacity for additional independent authorities.
    for requirement in requirements:
        matching = [item for item in candidates if _norm(item.evidence_class) == requirement]
        matching.sort(key=lambda item: _authority_score(item, jurisdiction, language, selected_domains), reverse=True)
        if not matching:
            continue
        choice = matching[0]
        selected.append(_selection(choice, jurisdiction, language, selected_domains))
        selected_ids.add(choice.authority_id)
        if choice.authority_domain:
            selected_domains.add(choice.authority_domain.casefold())
        covered.add(requirement)
        if len(selected) >= max_authorities:
            break

    if len(selected) < max_authorities:
        remaining = [item for item in candidates if item.authority_id not in selected_ids]
        remaining.sort(key=lambda item: _authority_score(item, jurisdiction, language, selected_domains), reverse=True)
        for item in remaining:
            if len(selected) >= max_authorities:
                break
            selected.append(_selection(item, jurisdiction, language, selected_domains))
            selected_ids.add(item.authority_id)
            if item.authority_domain:
                selected_domains.add(item.authority_domain.casefold())
            covered.add(_norm(item.evidence_class))

    uncovered = tuple(requirement for requirement in requirements if requirement not in covered)
    return OrchestrationPlan(
        orchestration_version=ORCHESTRATION_VERSION,
        selections=tuple(selected),
        uncovered_evidence_classes=uncovered,
        coverage_ratio=round(len(covered) / len(requirements), 6),
        interpretation=(
            "The planner prioritizes required evidence classes, jurisdiction/language fit, prior "
            "retrieval success and domain diversity. It schedules retrieval; it does not treat an "
            "authority selection as evidence or a factual verdict."
        ),
    )


def _selection(
    item: AuthorityOption,
    jurisdiction: str | None,
    language: str | None,
    selected_domains: set[str],
) -> AuthoritySelection:
    reasons: list[str] = ["required evidence class"]
    if jurisdiction and _norm(item.jurisdiction) == _norm(jurisdiction):
        reasons.append("jurisdiction match")
    if language and item.language and _norm(item.language) == _norm(language):
        reasons.append("language match")
    if item.authority_domain and item.authority_domain.casefold() not in selected_domains:
        reasons.append("independent authority domain")
    if item.prior_success_rate is not None:
        reasons.append("historical retrieval yield")
    if item.prior_attempted:
        reasons.append("repeat attempt penalized")
    return AuthoritySelection(
        authority_id=item.authority_id,
        evidence_class=_norm(item.evidence_class),
        score=round(_authority_score(item, jurisdiction, language, selected_domains), 6),
        reason=", ".join(reasons),
    )


def _authority_score(
    item: AuthorityOption,
    jurisdiction: str | None,
    language: str | None,
    selected_domains: set[str],
) -> float:
    score = 1.0
    if jurisdiction:
        if _norm(item.jurisdiction) == _norm(jurisdiction):
            score += 0.4
        elif _norm(item.jurisdiction) not in {"global", ""}:
            score -= 0.15
    if language and item.language:
        score += 0.2 if _norm(item.language) == _norm(language) else -0.05
    if item.authority_domain:
        score += 0.15 if item.authority_domain.casefold() not in selected_domains else -0.2
    if item.prior_success_rate is not None:
        score += 0.25 * max(0.0, min(1.0, float(item.prior_success_rate)))
    if item.prior_attempted:
        score -= 0.25
    return score


def _norm(value: str | None) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())
