from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

CLAIM_EXTRACTOR_VERSION = "deterministic-atomic-claim-extractor-v2"


class ClaimVerificationLabel(StrEnum):
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    MISLEADING = "misleading"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NOT_CHECKABLE = "not_checkable"


class ClaimType(StrEnum):
    NUMERIC = "numeric"
    TEMPORAL = "temporal"
    IDENTITY = "identity"
    LOCATION = "location"
    LEGAL = "legal"
    SCIENTIFIC = "scientific"
    CAUSAL = "causal"
    PREDICTION = "prediction"
    ATTRIBUTION = "attribution"
    EVENT_OCCURRENCE = "event_occurrence"
    COMPARATIVE = "comparative"
    STATISTICAL = "statistical"
    QUOTE = "quote"
    OPINION = "opinion"
    OTHER_FACTUAL = "other_factual"


_SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_NUMBER_PATTERN = re.compile(
    r"(?<!\w)(?P<currency>₹|\$|€|£|INR\s*|USD\s*|EUR\s*|GBP\s*)?"
    r"(?P<number>\d+(?:[.,]\d+)*)\s*"
    r"(?P<unit>%|percent|percentage points?|pp|bn|billion|mn|million|crore|lakh|thousand|k)?(?!\w)",
    re.I,
)
_DATE_PATTERN = re.compile(
    r"\b(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?)"
    r"|\b\d{4}\b"
    r"|\b(?:today|yesterday|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
_CAPITALIZED_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.+-]+|[A-Z]{2,})"
    r"(?:\s+[A-Z][A-Za-z0-9&.+-]+){0,4}"
)
_REPORTING_OR_ACTION_VERBS = {
    "accused",
    "announced",
    "approved",
    "blocked",
    "charged",
    "claimed",
    "confirmed",
    "declared",
    "denied",
    "disclosed",
    "filed",
    "found",
    "launched",
    "ordered",
    "published",
    "reported",
    "released",
    "said",
    "signed",
    "sued",
    "warned",
}
_SPECULATION_MARKERS = {
    "could",
    "may",
    "might",
    "possibly",
    "rumor",
    "rumour",
    "speculation",
    "unconfirmed",
}
_PREDICTION_MARKERS = {
    "expects",
    "expected",
    "forecast",
    "forecasted",
    "likely",
    "plans",
    "projected",
    "would",
}
_CAUSAL_MARKERS = {"because", "caused", "causes", "due to", "led to", "resulted in"}
_COMPARATIVE_MARKERS = {
    "higher than",
    "lower than",
    "more than",
    "less than",
    "largest",
    "smallest",
    "highest",
    "lowest",
    "record",
}
_LEGAL_MARKERS = {
    "appeal",
    "court",
    "judgment",
    "judge",
    "lawsuit",
    "order",
    "petition",
    "ruling",
    "sentence",
    "tribunal",
    "verdict",
}
_SCIENCE_MARKERS = {
    "clinical",
    "dataset",
    "experiment",
    "peer-reviewed",
    "research",
    "researchers",
    "scientists",
    "study",
    "trial",
}
_OPINION_MARKERS = {
    "believe",
    "believes",
    "feel",
    "feels",
    "opinion",
    "should",
    "think",
    "thinks",
}
_LOW_VALUE_PREFIXES = (
    "advertisement",
    "also read",
    "click here",
    "follow us",
    "read more",
    "subscribe",
)
_ATTRIBUTION_FRONT_PATTERN = re.compile(
    r"^(?P<speaker>[A-Z][^,]{1,100}?)\s+"
    r"(?P<verb>said|reported|announced|confirmed|denied|claimed|warned|disclosed|declared)\s+"
    r"(?:that\s+)?(?P<body>.+)$",
    re.I,
)
_ATTRIBUTION_TAIL_PATTERN = re.compile(
    r"^(?P<body>.+?)(?:,|\s+)\s*(?P<speaker>[A-Za-z][^,]{0,80}?)\s+"
    r"(?P<verb>said|reported|confirmed|claimed|warned)$",
    re.I,
)
_ATOMIC_CONJUNCTION_PATTERN = re.compile(
    r"\s+and\s+(?=(?:would|will|was|were|is|are|has|have|had|can|could|may|might|must)\b)",
    re.I,
)
_SUBJECT_BEFORE_MODAL_PATTERN = re.compile(
    r"^(?P<subject>.+?)\s+(?:would|will|was|were|is|are|has|have|had|can|could|may|might|must)\b",
    re.I,
)

_CURRENCY_CODES = {
    "₹": "INR",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "inr": "INR",
    "usd": "USD",
    "eur": "EUR",
    "gbp": "GBP",
}
_SCALE_FACTORS = {
    "k": 1_000,
    "thousand": 1_000,
    "lakh": 100_000,
    "mn": 1_000_000,
    "million": 1_000_000,
    "crore": 10_000_000,
    "bn": 1_000_000_000,
    "billion": 1_000_000_000,
}


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    text: str
    sentence_index: int
    features: dict[str, object]
    clause_index: int = 0
    source_sentence: str | None = None

    @property
    def claim_sha256(self) -> str:
        return claim_sha256(self.text)

    @property
    def canonical_key(self) -> str:
        value = self.features.get("canonical_key")
        return str(value) if value else claim_sha256(self.text)


def extract_claims(text: str, *, max_claims: int = 40) -> tuple[ExtractedClaim, ...]:
    """Extract conservative, atomic factual claims with deterministic metadata.

    This remains intentionally model-free so ingestion is reproducible. The extractor
    decomposes only conjunctions for which omitted subjects can be reconstructed safely;
    uncertain decomposition is left as one claim rather than inventing propositions.
    """

    claims: list[ExtractedClaim] = []
    for sentence_index, sentence in enumerate(split_sentences(text)):
        sentence_features = claim_features(sentence)
        if not sentence_features["is_claim_candidate"]:
            continue
        clauses = decompose_atomic_claims(sentence)
        for clause_index, clause in enumerate(clauses):
            features = claim_features(clause)
            features["source_sentence_index"] = sentence_index
            features["clause_index"] = clause_index
            features["source_sentence_sha256"] = claim_sha256(sentence)
            features["atomic_decomposition"] = len(clauses) > 1
            claims.append(
                ExtractedClaim(
                    text=clause,
                    sentence_index=sentence_index,
                    clause_index=clause_index,
                    source_sentence=sentence,
                    features=features,
                )
            )
            if len(claims) >= max_claims:
                return tuple(claims)
    return tuple(claims)


def split_sentences(text: str) -> tuple[str, ...]:
    normalized = _normalize_text(text)
    if not normalized:
        return ()
    rough_sentences = _SENTENCE_BOUNDARY_PATTERN.split(normalized)
    return tuple(
        sentence
        for sentence in (_normalize_text(item) for item in rough_sentences)
        if sentence
    )


def decompose_atomic_claims(sentence: str) -> tuple[str, ...]:
    """Conservatively split a compound factual sentence into atomic propositions."""

    normalized = _normalize_text(sentence)
    if not normalized:
        return ()
    terminal = normalized[-1] if normalized[-1:] in ".!?" else ""
    core = normalized[:-1] if terminal else normalized

    attribution = _extract_attribution(core)
    if attribution is not None:
        speaker, verb, body, position = attribution
        body_parts = _split_reconstructable_body(body)
        if len(body_parts) > 1:
            if position == "front":
                return tuple(
                    _ensure_terminal(f"{speaker} {verb} {part}", terminal or ".")
                    for part in body_parts
                )
            return tuple(
                _ensure_terminal(f"{part}, {speaker} {verb}", terminal or ".")
                for part in body_parts
            )

    body_parts = _split_reconstructable_body(core)
    if len(body_parts) > 1:
        return tuple(_ensure_terminal(part, terminal or ".") for part in body_parts)
    return (normalized,)


def claim_features(sentence: str) -> dict[str, object]:
    normalized = _normalize_text(sentence)
    lowered = normalized.lower()
    words = normalized.split()
    reporting_or_action_terms = sorted(
        term for term in _REPORTING_OR_ACTION_VERBS if re.search(rf"\b{re.escape(term)}\b", lowered)
    )
    speculation_terms = sorted(
        term for term in _SPECULATION_MARKERS if re.search(rf"\b{re.escape(term)}\b", lowered)
    )
    entities = tuple(
        entity
        for entity in {
            _normalize_text(match.group(0))
            for match in _CAPITALIZED_PATTERN.finditer(normalized)
        }
        if entity and entity.lower() not in {"the", "this", "after", "before"}
    )
    quantities = extract_quantities(normalized)
    temporal_references = extract_temporal_references(normalized)
    attribution = extract_attribution(normalized)
    has_number = bool(quantities)
    has_date = bool(temporal_references)
    starts_low_value = lowered.startswith(_LOW_VALUE_PREFIXES)
    word_count = len(words)
    high_value_signal_count = sum(
        [
            bool(reporting_or_action_terms),
            bool(entities),
            has_number,
            has_date,
            bool(attribution),
        ]
    )
    factual_verb = bool(reporting_or_action_terms) or bool(
        re.search(
            r"\b(?:is|are|was|were|has|have|had|rose|fell|increased|decreased|grew|declined|won|lost|began|ended|cost|reached|remains?)\b",
            lowered,
        )
    )
    is_claim_candidate = (
        6 <= word_count <= 100
        and not starts_low_value
        and not normalized.endswith("?")
        and (
            high_value_signal_count >= 2
            or (has_number and factual_verb)
            or (has_date and factual_verb)
        )
    )
    claim_type = classify_claim_type(normalized, quantities, temporal_references, attribution)
    checkability_score = _checkability_score(
        claim_type=claim_type,
        quantities=quantities,
        temporal_references=temporal_references,
        entities=entities,
        reporting_or_action_terms=reporting_or_action_terms,
        speculation_terms=speculation_terms,
    )
    canonical_text = canonicalize_claim_text(normalized)
    score = min(
        1.0,
        high_value_signal_count / 5
        + min(word_count, 40) / 200
        + checkability_score * 0.2,
    )
    if speculation_terms:
        score = max(0.0, score - 0.15)
    return {
        "word_count": word_count,
        "has_number": has_number,
        "has_date": has_date,
        "entities": sorted(entities),
        "entity_count": len(entities),
        "reporting_or_action_terms": reporting_or_action_terms,
        "speculation_terms": speculation_terms,
        "signal_count": high_value_signal_count,
        "score": round(score, 6),
        "is_claim_candidate": is_claim_candidate,
        "claim_type": claim_type.value,
        "quantities": list(quantities),
        "temporal_references": list(temporal_references),
        "attribution": attribution,
        "checkability_score": round(checkability_score, 6),
        "expected_primary_evidence": expected_primary_evidence(claim_type, normalized),
        "canonical_text": canonical_text,
        "canonical_key": claim_sha256(canonical_text),
        "claim_family_text": claim_family_text(normalized),
        "claim_family_key": claim_sha256(claim_family_text(normalized)),
    }


def classify_claim_type(
    sentence: str,
    quantities: tuple[dict[str, object], ...] | None = None,
    temporal_references: tuple[dict[str, object], ...] | None = None,
    attribution: dict[str, str] | None = None,
) -> ClaimType:
    lowered = sentence.lower()
    quantities = quantities if quantities is not None else extract_quantities(sentence)
    temporal_references = (
        temporal_references
        if temporal_references is not None
        else extract_temporal_references(sentence)
    )
    attribution = attribution if attribution is not None else extract_attribution(sentence)

    if any(marker in lowered for marker in _CAUSAL_MARKERS):
        return ClaimType.CAUSAL
    if any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in _PREDICTION_MARKERS):
        return ClaimType.PREDICTION
    if any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in _LEGAL_MARKERS):
        return ClaimType.LEGAL
    if any(marker in lowered for marker in _SCIENCE_MARKERS):
        return ClaimType.SCIENTIFIC
    if any(marker in lowered for marker in _COMPARATIVE_MARKERS):
        return ClaimType.COMPARATIVE
    if any(q.get("kind") in {"percentage", "currency", "scaled_number"} for q in quantities):
        return ClaimType.NUMERIC
    if quantities:
        return ClaimType.STATISTICAL
    if temporal_references:
        return ClaimType.TEMPORAL
    if attribution:
        return ClaimType.ATTRIBUTION
    if '"' in sentence or "“" in sentence or "”" in sentence:
        return ClaimType.QUOTE
    if any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in _OPINION_MARKERS):
        return ClaimType.OPINION
    return ClaimType.EVENT_OCCURRENCE


def extract_quantities(text: str) -> tuple[dict[str, object], ...]:
    results: list[dict[str, object]] = []
    date_spans = [match.span() for match in _DATE_PATTERN.finditer(text)]
    for match in _NUMBER_PATTERN.finditer(text):
        if any(_spans_overlap(match.span(), span) for span in date_spans):
            continue
        number_text = match.group("number")
        try:
            value = float(number_text.replace(",", ""))
        except ValueError:
            continue
        raw_currency = (match.group("currency") or "").strip()
        unit = (match.group("unit") or "").lower()
        currency = _CURRENCY_CODES.get(raw_currency.lower() if raw_currency else "")
        scale = _SCALE_FACTORS.get(unit, 1)
        normalized_value = value * scale
        if unit in {"%", "percent"}:
            kind = "percentage"
            normalized_unit = "percent"
        elif unit.startswith("percentage point") or unit == "pp":
            kind = "percentage_point"
            normalized_unit = "percentage_point"
        elif currency:
            kind = "currency"
            normalized_unit = currency
        elif scale != 1:
            kind = "scaled_number"
            normalized_unit = "count"
        else:
            kind = "number"
            normalized_unit = "count"
        results.append(
            {
                "raw": _normalize_text(match.group(0)),
                "value": value,
                "normalized_value": normalized_value,
                "kind": kind,
                "unit": normalized_unit,
                "currency": currency,
                "scale": scale,
            }
        )
    return tuple(results)


def extract_temporal_references(text: str) -> tuple[dict[str, object], ...]:
    results: list[dict[str, object]] = []
    for match in _DATE_PATTERN.finditer(text):
        raw = _normalize_text(match.group(0))
        lowered = raw.lower()
        year_match = re.search(r"\b(?:19|20)\d{2}\b", raw)
        if year_match:
            kind = "absolute"
            normalized = year_match.group(0)
        elif lowered in {"today", "yesterday", "tomorrow"}:
            kind = "relative"
            normalized = None
        elif lowered in {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }:
            kind = "weekday"
            normalized = None
        else:
            kind = "partial_date"
            normalized = None
        results.append({"raw": raw, "kind": kind, "normalized": normalized})
    return tuple(results)


def extract_attribution(text: str) -> dict[str, str] | None:
    normalized = _normalize_text(text).rstrip(".!?")
    match = _ATTRIBUTION_FRONT_PATTERN.match(normalized)
    if match:
        return {
            "speaker": _normalize_text(match.group("speaker")),
            "verb": match.group("verb").lower(),
            "position": "front",
        }
    match = _ATTRIBUTION_TAIL_PATTERN.match(normalized)
    if match:
        return {
            "speaker": _normalize_text(match.group("speaker")),
            "verb": match.group("verb").lower(),
            "position": "tail",
        }
    return None


def expected_primary_evidence(claim_type: ClaimType, sentence: str) -> list[str]:
    lowered = sentence.lower()
    if claim_type is ClaimType.LEGAL:
        return ["court_order_or_judgment", "official_case_record"]
    if claim_type is ClaimType.SCIENTIFIC:
        return ["research_paper", "dataset_or_registry", "institutional_statement"]
    if any(term in lowered for term in ("election", "vote", "ballot")):
        return ["election_authority_record"]
    if any(term in lowered for term in ("revenue", "profit", "earnings", "shares")):
        return ["regulatory_filing", "audited_financial_statement"]
    if any(term in lowered for term in ("ministry", "government", "policy", "budget")):
        return ["official_government_record", "gazette_or_order"]
    if claim_type in {ClaimType.NUMERIC, ClaimType.STATISTICAL, ClaimType.COMPARATIVE}:
        return ["primary_dataset", "official_statistical_release"]
    if claim_type is ClaimType.ATTRIBUTION:
        return ["original_statement", "transcript_or_recording"]
    if claim_type is ClaimType.PREDICTION:
        return ["original_forecast_or_statement"]
    return ["primary_record", "independent_reporting"]


def canonicalize_claim_text(text: str) -> str:
    normalized = _normalize_text(text).lower().strip(" .!?\"'“”")
    normalized = re.sub(r"\b(?:said|reported|according to)\b", " stated ", normalized)
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized)
    return normalized



def claim_family_text(text: str) -> str:
    """Normalize volatile quantities/dates so revisions of one proposition can be grouped."""

    normalized = canonicalize_claim_text(text)
    normalized = _DATE_PATTERN.sub(" <DATE> ", normalized)
    normalized = _NUMBER_PATTERN.sub(" <NUM> ", normalized)
    normalized = re.sub(r"\b(?:today|yesterday|tomorrow)\b", " <DATE> ", normalized)
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized)
    return normalized.strip()

def claim_sha256(text: str) -> str:
    return sha256(_normalize_text(text).lower().encode("utf-8")).hexdigest()


def _extract_attribution(text: str) -> tuple[str, str, str, str] | None:
    match = _ATTRIBUTION_FRONT_PATTERN.match(text)
    if match:
        return (
            _normalize_text(match.group("speaker")),
            match.group("verb").lower(),
            _normalize_text(match.group("body")),
            "front",
        )
    match = _ATTRIBUTION_TAIL_PATTERN.match(text)
    if match:
        return (
            _normalize_text(match.group("speaker")),
            match.group("verb").lower(),
            _normalize_text(match.group("body")),
            "tail",
        )
    return None


def _split_reconstructable_body(body: str) -> tuple[str, ...]:
    parts = _ATOMIC_CONJUNCTION_PATTERN.split(body)
    if len(parts) <= 1:
        return (body,)
    first = _normalize_text(parts[0])
    subject_match = _SUBJECT_BEFORE_MODAL_PATTERN.match(first)
    if subject_match is None:
        return (body,)
    subject = _normalize_text(subject_match.group("subject"))
    reconstructed = [first]
    for part in parts[1:]:
        clean = _normalize_text(part)
        if not clean:
            continue
        reconstructed.append(f"{subject} {clean}")
    return tuple(reconstructed) if len(reconstructed) == len(parts) else (body,)


def _checkability_score(
    *,
    claim_type: ClaimType,
    quantities: tuple[dict[str, object], ...],
    temporal_references: tuple[dict[str, object], ...],
    entities: tuple[str, ...],
    reporting_or_action_terms: list[str],
    speculation_terms: list[str],
) -> float:
    score = 0.2
    if entities:
        score += 0.2
    if quantities:
        score += 0.25
    if temporal_references:
        score += 0.15
    if reporting_or_action_terms:
        score += 0.1
    if claim_type in {
        ClaimType.NUMERIC,
        ClaimType.STATISTICAL,
        ClaimType.TEMPORAL,
        ClaimType.LEGAL,
        ClaimType.ATTRIBUTION,
        ClaimType.EVENT_OCCURRENCE,
    }:
        score += 0.1
    if claim_type in {ClaimType.OPINION, ClaimType.PREDICTION}:
        score -= 0.2
    if speculation_terms:
        score -= 0.15
    return min(1.0, max(0.0, score))


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _ensure_terminal(text: str, terminal: str) -> str:
    normalized = _normalize_text(text).rstrip(".!?")
    return f"{normalized}{terminal}"


def _normalize_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()
