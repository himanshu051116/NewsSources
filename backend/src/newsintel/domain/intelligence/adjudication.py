from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations

ADJUDICATION_METHODOLOGY_VERSION = "verification-adjudication-v1"


@dataclass(frozen=True, slots=True)
class AdjudicationReview:
    case_key: str
    reviewer_key: str
    label: str
    role: str = "reviewer"


@dataclass(frozen=True, slots=True)
class AdjudicationAgreement:
    methodology_version: str
    case_count: int
    review_count: int
    multi_review_case_count: int
    unanimous_case_count: int
    disagreement_case_count: int
    adjudicated_disagreement_count: int
    pairwise_agreement: float | None
    krippendorff_alpha_nominal: float | None
    label_counts: dict[str, int]
    reviewer_counts: dict[str, int]
    interpretation: str


@dataclass(frozen=True, slots=True)
class ConsensusDecision:
    case_key: str
    state: str
    label: str | None
    reviewer_count: int
    reviewer_labels: tuple[str, ...]
    adjudicator_label: str | None
    rationale: str


def assess_adjudication_agreement(reviews: tuple[AdjudicationReview, ...]) -> AdjudicationAgreement:
    by_case: dict[str, list[AdjudicationReview]] = defaultdict(list)
    label_counts: Counter[str] = Counter()
    reviewer_counts: Counter[str] = Counter()
    for review in reviews:
        case_key = str(review.case_key).strip()
        reviewer = str(review.reviewer_key).strip()
        label = _label(review.label)
        role = _role(review.role)
        if not case_key or not reviewer or not label:
            continue
        normalized = AdjudicationReview(case_key, reviewer, label, role)
        by_case[case_key].append(normalized)
        label_counts[label] += 1
        reviewer_counts[reviewer] += 1

    multi = 0
    unanimous = 0
    disagreements = 0
    adjudicated_disagreements = 0
    pair_agree = 0
    pair_total = 0
    nominal_rows: list[list[str]] = []

    for items in by_case.values():
        reviewer_items = [item for item in items if item.role == "reviewer"]
        labels = [item.label for item in reviewer_items]
        if len(labels) >= 2:
            multi += 1
            nominal_rows.append(labels)
            if len(set(labels)) == 1:
                unanimous += 1
            else:
                disagreements += 1
                if any(item.role == "adjudicator" for item in items):
                    adjudicated_disagreements += 1
            for left, right in combinations(labels, 2):
                pair_total += 1
                if left == right:
                    pair_agree += 1

    return AdjudicationAgreement(
        methodology_version=ADJUDICATION_METHODOLOGY_VERSION,
        case_count=len(by_case),
        review_count=sum(len(items) for items in by_case.values()),
        multi_review_case_count=multi,
        unanimous_case_count=unanimous,
        disagreement_case_count=disagreements,
        adjudicated_disagreement_count=adjudicated_disagreements,
        pairwise_agreement=_round(pair_agree / pair_total if pair_total else None),
        krippendorff_alpha_nominal=_round(_krippendorff_alpha_nominal(nominal_rows)),
        label_counts=dict(sorted(label_counts.items())),
        reviewer_counts=dict(sorted(reviewer_counts.items())),
        interpretation=(
            "Agreement metrics measure consistency between independent human adjudicators, not model "
            "accuracy. Pairwise agreement is the fraction of reviewer pairs that selected the same label. "
            "Nominal Krippendorff alpha adjusts observed disagreement for label prevalence and supports "
            "more than two reviewers. Disagreements should be resolved by a separate adjudicator rather "
            "than by exposing the model prediction to reviewers."
        ),
    )


def decide_consensus(
    case_key: str,
    reviews: tuple[AdjudicationReview, ...],
    *,
    min_independent_reviews: int = 2,
) -> ConsensusDecision:
    relevant = [item for item in reviews if item.case_key == case_key]
    reviewer_labels = [_label(item.label) for item in relevant if _role(item.role) == "reviewer" and _label(item.label)]
    adjudicator_labels = [_label(item.label) for item in relevant if _role(item.role) == "adjudicator" and _label(item.label)]
    adjudicator_label = adjudicator_labels[-1] if adjudicator_labels else None
    if len(reviewer_labels) < min_independent_reviews:
        return ConsensusDecision(case_key, "insufficient_reviews", None, len(reviewer_labels), tuple(reviewer_labels), adjudicator_label, "At least two independent reviewer labels are required.")
    unique = set(reviewer_labels)
    if len(unique) == 1:
        label = reviewer_labels[0]
        return ConsensusDecision(case_key, "consensus", label, len(reviewer_labels), tuple(reviewer_labels), adjudicator_label, "Independent reviewers agreed unanimously.")
    if adjudicator_label:
        return ConsensusDecision(case_key, "adjudicated", adjudicator_label, len(reviewer_labels), tuple(reviewer_labels), adjudicator_label, "Independent reviewers disagreed and a separate adjudicator resolved the case.")
    return ConsensusDecision(case_key, "disagreement", None, len(reviewer_labels), tuple(reviewer_labels), None, "Independent reviewers disagree; a separate adjudicator is required before finalization.")


def _krippendorff_alpha_nominal(rows: list[list[str]]) -> float | None:
    # Nominal alpha via observed/expected pair disagreement. Cases with fewer than two
    # independent reviews do not contribute to observed disagreement.
    observed_disagreements = 0.0
    observed_pairs = 0.0
    pooled: Counter[str] = Counter()
    total_labels = 0
    for labels in rows:
        if len(labels) < 2:
            continue
        pooled.update(labels)
        total_labels += len(labels)
        for left, right in combinations(labels, 2):
            observed_pairs += 1.0
            if left != right:
                observed_disagreements += 1.0
    if observed_pairs <= 0 or total_labels < 2:
        return None
    do = observed_disagreements / observed_pairs
    same_expected = sum(count * (count - 1) for count in pooled.values()) / (total_labels * (total_labels - 1))
    de = 1.0 - same_expected
    if de <= 1e-12:
        return 1.0 if do <= 1e-12 else None
    return max(-1.0, min(1.0, 1.0 - do / de))


def _label(value: str) -> str:
    return "_".join(str(value).strip().casefold().replace("-", "_").split())


def _role(value: str) -> str:
    normalized = str(value).strip().casefold()
    return "adjudicator" if normalized == "adjudicator" else "reviewer"


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
