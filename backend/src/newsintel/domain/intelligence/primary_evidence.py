from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from newsintel.domain.intelligence.claims import ClaimType, claim_features

PRIMARY_EVIDENCE_PLANNER_VERSION = "primary-evidence-requirement-planner-v1"


class EvidenceAuthorityClass(StrEnum):
    COURT_RECORD = "court_record"
    GOVERNMENT_RECORD = "government_record"
    GAZETTE_OR_ORDER = "gazette_or_order"
    REGULATORY_FILING = "regulatory_filing"
    AUDITED_FINANCIAL_STATEMENT = "audited_financial_statement"
    ELECTION_AUTHORITY_RECORD = "election_authority_record"
    OFFICIAL_DATASET = "official_dataset"
    DATASET_METHODOLOGY = "dataset_methodology"
    SCIENTIFIC_PAPER = "scientific_paper"
    STUDY_REGISTRY = "study_registry"
    INSTITUTIONAL_STATEMENT = "institutional_statement"
    ORIGINAL_STATEMENT = "original_statement"
    TRANSCRIPT_OR_RECORDING = "transcript_or_recording"
    COMPANY_FILING = "company_filing"
    PRIMARY_RECORD = "primary_record"
    INDEPENDENT_REPORTING = "independent_reporting"


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    evidence_class: EvidenceAuthorityClass
    priority: int
    required: bool
    rationale: str
    query_hints: tuple[str, ...]
    authority_hints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrimaryEvidencePlan:
    planner_version: str
    claim_type: str
    claim_text: str
    plan_key: str
    requirements: tuple[EvidenceRequirement, ...]
    search_terms: tuple[str, ...]
    completeness_criteria: dict[str, object]


def plan_primary_evidence(
    claim_text: str,
    *,
    extraction_features: dict[str, object] | None = None,
) -> PrimaryEvidencePlan:
    """Create an auditable evidence-retrieval plan without asserting that evidence exists."""

    features = extraction_features or claim_features(claim_text)
    claim_type = str(features.get("claim_type") or ClaimType.OTHER_FACTUAL.value)
    expected = features.get("expected_primary_evidence")
    expected_names = [str(item) for item in expected] if isinstance(expected, list) else []
    classes = _map_expected_classes(expected_names, claim_type, claim_text)
    search_terms = _search_terms(claim_text, features)
    requirements = tuple(
        EvidenceRequirement(
            evidence_class=evidence_class,
            priority=index + 1,
            required=index == 0,
            rationale=_rationale(evidence_class),
            query_hints=_query_hints(evidence_class, search_terms),
            authority_hints=_authority_hints(evidence_class),
        )
        for index, evidence_class in enumerate(classes)
    )
    plan_material = "|".join(
        [claim_type, claim_text.strip().lower(), *(item.value for item in classes)]
    )
    return PrimaryEvidencePlan(
        planner_version=PRIMARY_EVIDENCE_PLANNER_VERSION,
        claim_type=claim_type,
        claim_text=claim_text,
        plan_key=sha256(plan_material.encode("utf-8")).hexdigest(),
        requirements=requirements,
        search_terms=search_terms,
        completeness_criteria={
            "minimum_primary_records": 1 if classes and classes[0] is not EvidenceAuthorityClass.INDEPENDENT_REPORTING else 0,
            "minimum_independent_lineages": 2,
            "require_counterevidence_search": True,
            "absence_is_not_contradiction": True,
            "temporal_alignment_required": True,
        },
    )


def _map_expected_classes(
    expected: list[str],
    claim_type: str,
    claim_text: str,
) -> tuple[EvidenceAuthorityClass, ...]:
    mapping = {
        "court_order_or_judgment": EvidenceAuthorityClass.COURT_RECORD,
        "official_case_record": EvidenceAuthorityClass.COURT_RECORD,
        "research_paper": EvidenceAuthorityClass.SCIENTIFIC_PAPER,
        "dataset_or_registry": EvidenceAuthorityClass.STUDY_REGISTRY,
        "institutional_statement": EvidenceAuthorityClass.INSTITUTIONAL_STATEMENT,
        "election_authority_record": EvidenceAuthorityClass.ELECTION_AUTHORITY_RECORD,
        "regulatory_filing": EvidenceAuthorityClass.REGULATORY_FILING,
        "audited_financial_statement": EvidenceAuthorityClass.AUDITED_FINANCIAL_STATEMENT,
        "official_government_record": EvidenceAuthorityClass.GOVERNMENT_RECORD,
        "gazette_or_order": EvidenceAuthorityClass.GAZETTE_OR_ORDER,
        "primary_dataset": EvidenceAuthorityClass.OFFICIAL_DATASET,
        "official_statistical_release": EvidenceAuthorityClass.OFFICIAL_DATASET,
        "original_statement": EvidenceAuthorityClass.ORIGINAL_STATEMENT,
        "transcript_or_recording": EvidenceAuthorityClass.TRANSCRIPT_OR_RECORDING,
        "original_forecast_or_statement": EvidenceAuthorityClass.ORIGINAL_STATEMENT,
        "primary_record": EvidenceAuthorityClass.PRIMARY_RECORD,
        "independent_reporting": EvidenceAuthorityClass.INDEPENDENT_REPORTING,
    }
    ordered: list[EvidenceAuthorityClass] = []
    for item in expected:
        mapped = mapping.get(item)
        if mapped is not None and mapped not in ordered:
            ordered.append(mapped)

    lowered = claim_text.lower()
    if any(term in lowered for term in ("company", "revenue", "profit", "earnings")):
        if EvidenceAuthorityClass.REGULATORY_FILING not in ordered:
            ordered.insert(0, EvidenceAuthorityClass.REGULATORY_FILING)
    if claim_type in {ClaimType.STATISTICAL.value, ClaimType.NUMERIC.value, ClaimType.COMPARATIVE.value}:
        if EvidenceAuthorityClass.OFFICIAL_DATASET not in ordered:
            ordered.append(EvidenceAuthorityClass.OFFICIAL_DATASET)
    if not ordered:
        ordered = [EvidenceAuthorityClass.PRIMARY_RECORD, EvidenceAuthorityClass.INDEPENDENT_REPORTING]
    if EvidenceAuthorityClass.INDEPENDENT_REPORTING not in ordered:
        ordered.append(EvidenceAuthorityClass.INDEPENDENT_REPORTING)
    return tuple(ordered)


def _search_terms(claim_text: str, features: dict[str, object]) -> tuple[str, ...]:
    entities = features.get("entities")
    terms: list[str] = []
    if isinstance(entities, list):
        terms.extend(str(item).strip() for item in entities if str(item).strip())
    attribution = features.get("attribution")
    if isinstance(attribution, dict):
        speaker = attribution.get("speaker")
        if isinstance(speaker, str) and speaker.strip():
            terms.append(speaker.strip())
    # Add a compact predicate phrase after removing volatile numeric/date tokens.
    predicate = re.sub(r"\b\d[\d,.]*\b", " ", claim_text)
    predicate = re.sub(r"[^\w\s\u0300-\u036F\u0900-\u097F-]", " ", predicate)
    predicate = " ".join(predicate.split())
    if predicate:
        terms.append(predicate[:180])
    deduped: list[str] = []
    for term in terms:
        if term.lower() not in {item.lower() for item in deduped}:
            deduped.append(term)
    return tuple(deduped[:8])


def _rationale(evidence_class: EvidenceAuthorityClass) -> str:
    return {
        EvidenceAuthorityClass.COURT_RECORD: "Use the operative court/judicial record rather than summaries when resolving legal claims.",
        EvidenceAuthorityClass.GOVERNMENT_RECORD: "Prefer the responsible public authority's record for government action or policy claims.",
        EvidenceAuthorityClass.GAZETTE_OR_ORDER: "Use the legally operative notification/order where one exists.",
        EvidenceAuthorityClass.REGULATORY_FILING: "Prefer a regulator/stock-exchange filing for company financial or material-event claims.",
        EvidenceAuthorityClass.AUDITED_FINANCIAL_STATEMENT: "Use audited statements for reported financial results and period comparisons.",
        EvidenceAuthorityClass.ELECTION_AUTHORITY_RECORD: "Use the competent election authority for official vote/result claims.",
        EvidenceAuthorityClass.OFFICIAL_DATASET: "Use the originating statistical dataset/release and retain the measurement period and denominator.",
        EvidenceAuthorityClass.DATASET_METHODOLOGY: "Check methodology and revisions before comparing statistical values.",
        EvidenceAuthorityClass.SCIENTIFIC_PAPER: "Use the original paper/preprint and distinguish findings from later reporting.",
        EvidenceAuthorityClass.STUDY_REGISTRY: "Use a study/trial registry or dataset record to confirm protocol/status details.",
        EvidenceAuthorityClass.INSTITUTIONAL_STATEMENT: "Use the responsible institution's direct statement for attribution and status claims.",
        EvidenceAuthorityClass.ORIGINAL_STATEMENT: "Resolve attribution against the original statement or first-party publication.",
        EvidenceAuthorityClass.TRANSCRIPT_OR_RECORDING: "Use a transcript/recording when exact wording materially affects the claim.",
        EvidenceAuthorityClass.COMPANY_FILING: "Use a first-party filing carrying formal disclosure obligations.",
        EvidenceAuthorityClass.PRIMARY_RECORD: "Seek the closest available record created by the actor or authority responsible for the underlying fact.",
        EvidenceAuthorityClass.INDEPENDENT_REPORTING: "Use independent reporting as corroboration, not as a substitute for available primary records.",
    }[evidence_class]


def _query_hints(
    evidence_class: EvidenceAuthorityClass,
    search_terms: tuple[str, ...],
) -> tuple[str, ...]:
    suffixes = {
        EvidenceAuthorityClass.COURT_RECORD: ("judgment order case record",),
        EvidenceAuthorityClass.GOVERNMENT_RECORD: ("official notification ministry department",),
        EvidenceAuthorityClass.GAZETTE_OR_ORDER: ("gazette notification order",),
        EvidenceAuthorityClass.REGULATORY_FILING: ("exchange filing regulatory filing",),
        EvidenceAuthorityClass.AUDITED_FINANCIAL_STATEMENT: ("annual report audited financial results",),
        EvidenceAuthorityClass.ELECTION_AUTHORITY_RECORD: ("official election results",),
        EvidenceAuthorityClass.OFFICIAL_DATASET: ("official data statistical release methodology",),
        EvidenceAuthorityClass.DATASET_METHODOLOGY: ("methodology technical note revisions",),
        EvidenceAuthorityClass.SCIENTIFIC_PAPER: ("paper DOI study",),
        EvidenceAuthorityClass.STUDY_REGISTRY: ("trial registry dataset accession",),
        EvidenceAuthorityClass.INSTITUTIONAL_STATEMENT: ("official statement",),
        EvidenceAuthorityClass.ORIGINAL_STATEMENT: ("statement transcript speech",),
        EvidenceAuthorityClass.TRANSCRIPT_OR_RECORDING: ("transcript recording",),
        EvidenceAuthorityClass.COMPANY_FILING: ("company filing disclosure",),
        EvidenceAuthorityClass.PRIMARY_RECORD: ("official primary record",),
        EvidenceAuthorityClass.INDEPENDENT_REPORTING: ("independent report",),
    }[evidence_class]
    stem = " ".join(search_terms[:3]).strip()
    return tuple(f"{stem} {suffix}".strip() for suffix in suffixes)


def _authority_hints(evidence_class: EvidenceAuthorityClass) -> tuple[str, ...]:
    return {
        EvidenceAuthorityClass.COURT_RECORD: ("judiciary", "court registry"),
        EvidenceAuthorityClass.GOVERNMENT_RECORD: ("government department", "ministry", "public authority"),
        EvidenceAuthorityClass.GAZETTE_OR_ORDER: ("official gazette", "issuing authority"),
        EvidenceAuthorityClass.REGULATORY_FILING: ("securities regulator", "stock exchange"),
        EvidenceAuthorityClass.AUDITED_FINANCIAL_STATEMENT: ("issuer investor relations", "auditor-signed report"),
        EvidenceAuthorityClass.ELECTION_AUTHORITY_RECORD: ("election commission/authority",),
        EvidenceAuthorityClass.OFFICIAL_DATASET: ("national statistics office", "responsible public dataset owner"),
        EvidenceAuthorityClass.DATASET_METHODOLOGY: ("dataset owner",),
        EvidenceAuthorityClass.SCIENTIFIC_PAPER: ("journal", "institutional repository", "DOI registry"),
        EvidenceAuthorityClass.STUDY_REGISTRY: ("study/trial registry",),
        EvidenceAuthorityClass.INSTITUTIONAL_STATEMENT: ("responsible institution",),
        EvidenceAuthorityClass.ORIGINAL_STATEMENT: ("speaker/organization first-party channel",),
        EvidenceAuthorityClass.TRANSCRIPT_OR_RECORDING: ("official transcript", "full recording"),
        EvidenceAuthorityClass.COMPANY_FILING: ("company filing portal",),
        EvidenceAuthorityClass.PRIMARY_RECORD: ("originating authority",),
        EvidenceAuthorityClass.INDEPENDENT_REPORTING: ("independent publisher",),
    }[evidence_class]
