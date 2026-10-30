from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

ACCURACY_DIAGNOSTIC_VERSION = "accuracy-failure-attribution-v1"


@dataclass(frozen=True, slots=True)
class DiagnosticCase:
    case_key: str
    predicted_label: str
    adjudicated_label: str
    predicted_confidence: float
    topic_key: str | None = None
    language: str | None = None
    source_key: str | None = None
    extraction_fidelity_label: str | None = None
    event_assignment_state: str | None = None
    evidence_count: int = 0
    independent_lineage_count: int = 0
    primary_evidence_count: int = 0
    retrieval_complete: bool = False
    unresolved_conflict: bool = False


@dataclass(frozen=True, slots=True)
class AccuracyDiagnosticAssessment:
    methodology_version: str
    case_count: int
    error_count: int
    error_rate: float
    taxonomy_counts: dict[str, int]
    topic_error_rates: dict[str, float]
    language_error_rates: dict[str, float]
    source_error_rates: dict[str, float]
    high_confidence_error_count: int
    interpretation: str


def assess_accuracy_failures(cases: tuple[DiagnosticCase, ...]) -> AccuracyDiagnosticAssessment:
    taxonomy: Counter[str] = Counter()
    slice_totals: dict[str, Counter[str]] = {
        "topic": Counter(), "language": Counter(), "source": Counter()
    }
    slice_errors: dict[str, Counter[str]] = {
        "topic": Counter(), "language": Counter(), "source": Counter()
    }
    errors = 0
    high_conf = 0

    for case in cases:
        predicted = _norm(case.predicted_label)
        truth = _norm(case.adjudicated_label)
        if not predicted or not truth:
            continue
        dims = {
            "topic": _norm(case.topic_key or "unknown"),
            "language": _norm(case.language or "unknown"),
            "source": _norm(case.source_key or "unknown"),
        }
        for dim, key in dims.items():
            slice_totals[dim][key] += 1
        if predicted == truth:
            continue
        errors += 1
        if float(case.predicted_confidence) >= 0.8:
            high_conf += 1
        for dim, key in dims.items():
            slice_errors[dim][key] += 1
        taxonomy[_classify(case)] += 1

    count = len(cases)
    return AccuracyDiagnosticAssessment(
        methodology_version=ACCURACY_DIAGNOSTIC_VERSION,
        case_count=count,
        error_count=errors,
        error_rate=round(errors / count, 6) if count else 0.0,
        taxonomy_counts=dict(sorted(taxonomy.items())),
        topic_error_rates=_rates(slice_totals["topic"], slice_errors["topic"]),
        language_error_rates=_rates(slice_totals["language"], slice_errors["language"]),
        source_error_rates=_rates(slice_totals["source"], slice_errors["source"]),
        high_confidence_error_count=high_conf,
        interpretation=(
            "Failure attribution is diagnostic, not causal proof. It assigns each wrong benchmark verdict "
            "to the strongest observable upstream weakness (extraction, event identity, evidence retrieval, "
            "independence/primary-evidence coverage, conflict resolution, or verification decision). Use it "
            "to prioritize manual review and engineering investigation rather than to automatically rewrite verdicts."
        ),
    )


def _classify(case: DiagnosticCase) -> str:
    fidelity = _norm(case.extraction_fidelity_label or "")
    if fidelity == "weak":
        return "extraction_fidelity"
    event_state = _norm(case.event_assignment_state or "")
    if event_state in {"provisional", "candidate", "uncertain", "unassigned"}:
        return "event_identity"
    if not case.retrieval_complete or case.evidence_count <= 0:
        return "evidence_retrieval"
    if case.primary_evidence_count <= 0 and case.independent_lineage_count < 2:
        return "evidence_independence"
    if case.unresolved_conflict:
        return "conflict_resolution"
    return "verification_decision"


def _rates(total: Counter[str], errors: Counter[str]) -> dict[str, float]:
    return {
        key: round(errors.get(key, 0) / count, 6)
        for key, count in sorted(total.items())
        if count > 0
    }


def _norm(value: str) -> str:
    return "_".join(str(value).strip().casefold().replace("-", "_").split())
