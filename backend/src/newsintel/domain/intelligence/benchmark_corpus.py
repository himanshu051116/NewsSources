from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

BENCHMARK_CORPUS_AUDIT_VERSION = "verification-benchmark-corpus-audit-v2"


@dataclass(frozen=True, slots=True)
class BenchmarkCorpusCase:
    case_key: str | None
    claim_key: str | None
    split: str
    adjudicated_label: str
    topic_key: str | None = None
    language: str | None = None
    jurisdiction: str | None = None
    adjudicator_count: int = 1
    weight: float = 1.0
    group_key: str | None = None
    source_document_key: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkCorpusAudit:
    audit_version: str
    case_count: int
    effective_weight: float
    split_counts: dict[str, int]
    label_counts: dict[str, int]
    topic_counts: dict[str, int]
    language_counts: dict[str, int]
    jurisdiction_counts: dict[str, int]
    leakage_keys: tuple[str, ...]
    leakage_case_count: int
    duplicate_within_split_keys: tuple[str, ...]
    group_leakage_keys: tuple[str, ...]
    source_document_leakage_keys: tuple[str, ...]
    single_adjudicator_ratio: float | None
    readiness: str
    warnings: tuple[str, ...]
    interpretation: str


def audit_benchmark_corpus(cases: tuple[BenchmarkCorpusCase, ...]) -> BenchmarkCorpusAudit:
    split_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    jurisdiction_counts: Counter[str] = Counter()
    keys_to_splits: dict[str, set[str]] = defaultdict(set)
    groups_to_splits: dict[str, set[str]] = defaultdict(set)
    documents_to_splits: dict[str, set[str]] = defaultdict(set)
    key_split_counts: Counter[tuple[str, str]] = Counter()
    effective_weight = 0.0
    single_adjudicator_weight = 0.0
    identities: list[str] = []

    for index, case in enumerate(cases):
        split = _norm(case.split) or "unspecified"
        label = _norm(case.adjudicated_label) or "unknown"
        key = _case_identity(case, index)
        identities.append(key)
        weight = max(0.0, float(case.weight))
        effective_weight += weight
        if case.adjudicator_count <= 1:
            single_adjudicator_weight += weight
        split_counts[split] += 1
        label_counts[label] += 1
        if case.topic_key:
            topic_counts[_norm(case.topic_key)] += 1
        if case.language:
            language_counts[_norm(case.language)] += 1
        if case.jurisdiction:
            jurisdiction_counts[_norm(case.jurisdiction)] += 1
        keys_to_splits[key].add(split)
        key_split_counts[(key, split)] += 1
        if case.group_key and case.group_key.strip():
            groups_to_splits[_norm_key(case.group_key)].add(split)
        if case.source_document_key and case.source_document_key.strip():
            documents_to_splits[_norm_key(case.source_document_key)].add(split)

    leakage = tuple(sorted(key for key, splits in keys_to_splits.items() if len(splits) > 1))
    duplicates = tuple(sorted({key for (key, _), count in key_split_counts.items() if count > 1}))
    group_leakage = tuple(sorted(key for key, splits in groups_to_splits.items() if len(splits) > 1))
    document_leakage = tuple(sorted(key for key, splits in documents_to_splits.items() if len(splits) > 1))
    leakage_case_count = sum(1 for key in identities if key in leakage) if leakage else 0
    warnings: list[str] = []
    if leakage:
        warnings.append("The same benchmark identity appears in multiple splits; this can leak evaluation cases into development/tuning data.")
    if group_leakage:
        warnings.append("Related benchmark cases share a group_key across splits; event/family-level leakage can inflate held-out performance.")
    if document_leakage:
        warnings.append("Cases derived from the same source document appear across splits; paraphrase-level leakage can inflate held-out performance.")
    if duplicates:
        warnings.append("Duplicate benchmark identities exist within at least one split; aggregate metrics may overweight repeated cases.")
    single_ratio = single_adjudicator_weight / effective_weight if effective_weight > 0 else None
    if single_ratio is not None and single_ratio > 0.5:
        warnings.append("More than half of benchmark weight has a single recorded adjudicator; high-stakes calibration should use stronger independent adjudication where feasible.")
    if not split_counts.get("test") and len(split_counts) <= 1:
        warnings.append("No explicit held-out test split is recorded.")
    readiness = (
        "ready"
        if not leakage and not group_leakage and not document_leakage and len(cases) >= 30 and len(label_counts) >= 2
        else "needs_review"
    )
    return BenchmarkCorpusAudit(
        audit_version=BENCHMARK_CORPUS_AUDIT_VERSION,
        case_count=len(cases),
        effective_weight=round(effective_weight, 6),
        split_counts=dict(sorted(split_counts.items())),
        label_counts=dict(sorted(label_counts.items())),
        topic_counts=dict(sorted(topic_counts.items())),
        language_counts=dict(sorted(language_counts.items())),
        jurisdiction_counts=dict(sorted(jurisdiction_counts.items())),
        leakage_keys=leakage,
        leakage_case_count=leakage_case_count,
        duplicate_within_split_keys=duplicates,
        group_leakage_keys=group_leakage,
        source_document_leakage_keys=document_leakage,
        single_adjudicator_ratio=round(single_ratio, 6) if single_ratio is not None else None,
        readiness=readiness,
        warnings=tuple(warnings),
        interpretation=(
            "The corpus audit checks identity, group/event and source-document split hygiene plus benchmark composition. "
            "It does not certify adjudicated labels or representativeness; those remain dataset-governance responsibilities."
        ),
    )


def _case_identity(case: BenchmarkCorpusCase, index: int) -> str:
    if case.case_key and case.case_key.strip():
        return f"case:{case.case_key.strip().casefold()}"
    if case.claim_key and case.claim_key.strip():
        return f"claim:{case.claim_key.strip().casefold()}"
    return f"row:{index}"


def _norm_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _norm(value: str | None) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())
