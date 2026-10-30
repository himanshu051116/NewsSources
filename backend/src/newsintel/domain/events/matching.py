import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from newsintel.domain.events.assignment import EventCandidate

# v4 intentionally describes itself as structured lexical matching. It does not
# claim embedding/semantic behaviour that the implementation does not provide.
POLICY_VERSION = "event-matching-structured-lexical-v4"

_CAPITALIZED_PHRASE_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.+-]+|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z0-9&.+-]+|[A-Z]{2,})){0,4}"
)
_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,7}|[A-Z]{2,8}-\d+|[A-Z]{2,8}|\d+(?:\.\d+)?%?)\b"
)
_LOCATION_TERMS = {
    "afghanistan", "africa", "america", "australia", "bangalore", "beijing",
    "bengaluru", "bihar", "brazil", "britain", "canada", "china", "delhi",
    "europe", "france", "gaza", "germany", "gujarat", "india", "iran",
    "israel", "japan", "karnataka", "kerala", "kolkata", "london",
    "maharashtra", "mumbai", "new york", "odisha", "paradip", "bay of bengal",
    "assam", "hokkaido", "kyushu",
    "pakistan", "paris", "punjab", "russia", "singapore", "sriharikota", "tel aviv", "tokyo",
    "uk", "ukraine", "united kingdom",
    "united states", "us", "usa", "washington",
    # Common Hindi forms so source discovery and event matching do not diverge.
    "भारत", "दिल्ली", "मुंबई", "असम", "पाकिस्तान", "चीन", "रूस", "यूक्रेन",
}
_BROAD_LOCATION_TERMS = {
    "africa", "america", "australia", "brazil", "britain", "canada", "china",
    "europe", "france", "germany", "india", "iran", "israel", "japan", "pakistan",
    "russia", "uk", "ukraine", "united kingdom", "united states", "us", "usa",
    "भारत", "पाकिस्तान", "चीन", "रूस", "यूक्रेन",
}
_ENTITY_IGNORE_TERMS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "authorities", "authority", "strong", "fire", "three", "two", "one", "company",
    "court", "bank", "government", "ministry",
}
_STOPWORDS = {
    "about", "after", "again", "against", "also", "amid", "among", "and",
    "are", "around", "as", "at", "be", "been", "before", "being", "between",
    "but", "by", "can", "could", "during", "for", "from", "had", "has",
    "have", "he", "her", "his", "how", "in", "into", "is", "it", "its",
    "may", "more", "new", "not", "of", "on", "or", "over", "said", "says",
    "she", "that", "the", "their", "they", "this", "to", "up", "was", "were",
    "what", "when", "which", "while", "who", "will", "with",
    "और", "का", "की", "के", "को", "में", "से", "पर", "है", "हैं", "था",
    "थी", "ने", "यह", "वह", "एक", "लिए", "बाद", "तक", "भी",
}

_EVENT_TYPE_RULES: dict[str, frozenset[str]] = {
    "election": frozenset({"election", "vote", "voting", "ballot", "poll", "elected", "चुनाव", "मतदान"}),
    "legal": frozenset({"court", "judge", "judgment", "ruling", "lawsuit", "appeal", "verdict", "supreme", "highcourt", "अदालत", "न्यायालय", "फैसला"}),
    "policy": frozenset({"policy", "bill", "law", "regulation", "ministry", "cabinet", "government", "scheme", "नीति", "विधेयक", "सरकार", "मंत्रालय"}),
    "business": frozenset({"earnings", "revenue", "profit", "merger", "acquisition", "ipo", "shares", "company", "quarter", "कंपनी", "मुनाफा", "राजस्व"}),
    "security_conflict": frozenset({"attack", "war", "strike", "missile", "military", "troops", "ceasefire", "blast", "killed", "hijack", "hijacked", "pirates", "armed", "हमला", "युद्ध", "सेना", "विस्फोट"}),
    "disaster": frozenset({"earthquake", "flood", "cyclone", "storm", "fire", "landslide", "disaster", "भूकंप", "बाढ़", "चक्रवात", "आग"}),
    "maritime_incident": frozenset({"ship", "ships", "vessel", "vessels", "cargo", "sank", "sink", "sinks", "sinking", "capsize", "capsized", "collision", "grounded", "maritime", "hijack", "hijacked", "समुद्री", "जहाज", "डूबा"}),
    "health": frozenset({"health", "disease", "virus", "outbreak", "vaccine", "hospital", "patients", "स्वास्थ्य", "बीमारी", "वायरस", "टीका"}),
    "science_technology": frozenset({"research", "study", "scientists", "technology", "software", "ai", "space", "satellite", "launch", "अनुसंधान", "तकनीक", "अंतरिक्ष", "उपग्रह"}),
    "sports": frozenset({"match", "tournament", "league", "goal", "wicket", "cricket", "football", "खेल", "मैच", "क्रिकेट"}),
    "economy": frozenset({"inflation", "gdp", "economy", "rate", "repo", "bank", "budget", "unemployment", "महंगाई", "अर्थव्यवस्था", "बजट", "बैंक"}),
}
_NUMBER_WORDS = frozenset({
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty",
})
_ACTION_TERMS = frozenset({
    "announce", "announced", "approve", "approved", "ban", "banned", "launch",
    "launched", "attack", "attacked", "kill", "killed", "arrest", "arrested",
    "resign", "resigned", "win", "won", "lose", "lost", "increase", "increased",
    "decrease", "decreased", "cut", "raise", "raised", "sign", "signed", "meet",
    "met", "reject", "rejected", "confirm", "confirmed", "order", "ordered",
    "sink", "sinks", "sank", "sinking", "capsize", "capsized", "rescue", "rescued",
    "depart", "departed",
    "घोषणा", "घोषित", "मंजूर", "हमला", "गिरफ्तार", "जीत", "हारा", "बढ़ा",
    "घटा", "शुरू", "जारी", "आदेश",
})


@dataclass(frozen=True, slots=True)
class ArticleEventProfile:
    title: str
    text: str
    published_at: datetime | None = None
    observed_at: datetime | None = None
    title_tokens: frozenset[str] = field(init=False)
    content_tokens: frozenset[str] = field(init=False)
    title_shingles: frozenset[str] = field(init=False)
    content_shingles: frozenset[str] = field(init=False)
    entities: frozenset[str] = field(init=False)
    identifiers: frozenset[str] = field(init=False)
    locations: frozenset[str] = field(init=False)
    event_types: frozenset[str] = field(init=False)
    actions: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        text = f"{self.title}\n{self.text}"
        title_token_sequence = _tokens(self.title)
        content_token_sequence = _tokens(text)
        object.__setattr__(self, "title_tokens", frozenset(title_token_sequence))
        object.__setattr__(self, "content_tokens", frozenset(content_token_sequence))
        object.__setattr__(self, "title_shingles", _shingles(title_token_sequence, size=2))
        object.__setattr__(self, "content_shingles", _shingles(content_token_sequence, size=3))
        object.__setattr__(self, "entities", frozenset(_entities(text)))
        object.__setattr__(self, "identifiers", frozenset(_identifiers(text)))
        object.__setattr__(self, "locations", frozenset(_locations(text)))
        object.__setattr__(self, "event_types", frozenset(_event_types(content_token_sequence)))
        object.__setattr__(self, "actions", frozenset(token for token in content_token_sequence if token in _ACTION_TERMS))


@dataclass(frozen=True, slots=True)
class EventReference:
    event_id: UUID
    title: str
    text: str
    first_detected_at: datetime
    latest_observed_at: datetime | None = None

    @property
    def profile(self) -> ArticleEventProfile:
        return ArticleEventProfile(
            title=self.title,
            text=self.text,
            observed_at=self.latest_observed_at or self.first_detected_at,
        )


def build_event_candidates(
    incoming: ArticleEventProfile,
    references: Sequence[EventReference],
    *,
    limit: int = 20,
) -> tuple[EventCandidate, ...]:
    candidates = [_candidate_for_reference(incoming, reference) for reference in references]
    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    return tuple(ranked[:limit])


def event_candidate_features(candidate: EventCandidate) -> dict[str, float]:
    return {
        # Kept for API compatibility. Since v2 this field is a structured lexical
        # similarity feature, not an embedding-derived semantic score.
        "semantic_similarity": round(candidate.semantic_similarity, 6),
        "structured_lexical_similarity": round(candidate.semantic_similarity, 6),
        "title_similarity": round(candidate.title_similarity, 6),
        "entity_overlap": round(candidate.entity_overlap, 6),
        "identifier_overlap": round(candidate.identifier_overlap, 6),
        "claim_overlap": round(candidate.claim_overlap, 6),
        "temporal_compatibility": round(candidate.temporal_compatibility, 6),
        "geographic_compatibility": round(candidate.geographic_compatibility, 6),
        "event_type_compatibility": round(candidate.event_type_compatibility, 6),
        "anchor_overlap": round(candidate.anchor_overlap, 6),
        "score": round(candidate.score, 6),
    }


def provisional_event_features(candidates: Sequence[EventCandidate]) -> dict[str, float]:
    if not candidates:
        return {"candidate_count": 0.0}
    best = candidates[0]
    return {
        "candidate_count": float(len(candidates)),
        "best_rejected_score": round(best.score, 6),
        "best_rejected_semantic_similarity": round(best.semantic_similarity, 6),
        "best_rejected_title_similarity": round(best.title_similarity, 6),
        "best_rejected_event_type_compatibility": round(best.event_type_compatibility, 6),
        "best_rejected_anchor_overlap": round(best.anchor_overlap, 6),
    }


def _candidate_for_reference(incoming: ArticleEventProfile, reference: EventReference) -> EventCandidate:
    existing = reference.profile
    token_similarity = _weighted_similarity(
        incoming.content_tokens,
        existing.content_tokens,
        incoming.content_shingles,
        existing.content_shingles,
    )
    action_overlap = _overlap_or_unknown(incoming.actions, existing.actions)
    # Containment matters for wire-vs-original comparisons where one publisher
    # provides a short bulletin and another adds substantial context.  Jaccard
    # alone penalises the longer report even when the shorter report is almost
    # entirely contained within it.
    containment_similarity = _containment_similarity(
        incoming.content_tokens,
        existing.content_tokens,
        incoming.content_shingles,
        existing.content_shingles,
    )
    structured_similarity = min(
        1.0,
        0.65 * token_similarity
        + 0.20 * containment_similarity
        + 0.15 * action_overlap,
    )
    title_similarity = _weighted_similarity(
        incoming.title_tokens,
        existing.title_tokens,
        incoming.title_shingles,
        existing.title_shingles,
        token_weight=0.7,
        shingle_weight=0.3,
    )
    entity_overlap = _overlap_or_zero(incoming.entities, existing.entities)
    identifier_overlap = _overlap_or_zero(incoming.identifiers, existing.identifiers)
    geographic_compatibility = _geographic_compatibility(incoming.locations, existing.locations)
    event_type_compatibility = _event_type_compatibility(incoming.event_types, existing.event_types)
    temporal_compatibility = _temporal_compatibility(
        incoming.published_at or incoming.observed_at,
        existing.observed_at or reference.first_detected_at,
    )
    anchor_overlap = _anchor_overlap(
        entity_overlap=entity_overlap,
        identifier_overlap=identifier_overlap,
        geographic_compatibility=(
            geographic_compatibility if incoming.locations and existing.locations else 0.0
        ),
        event_type_compatibility=(
            event_type_compatibility if incoming.event_types and existing.event_types else 0.0
        ),
        action_overlap=(action_overlap if incoming.actions and existing.actions else 0.0),
        title_containment=_containment(incoming.title_tokens, existing.title_tokens),
        content_containment=_containment(incoming.content_tokens, existing.content_tokens),
    )
    return EventCandidate(
        event_id=reference.event_id,
        semantic_similarity=structured_similarity,
        title_similarity=title_similarity,
        entity_overlap=entity_overlap,
        identifier_overlap=identifier_overlap,
        claim_overlap=_jaccard(incoming.content_shingles, existing.content_shingles),
        temporal_compatibility=temporal_compatibility,
        geographic_compatibility=geographic_compatibility,
        event_type_compatibility=event_type_compatibility,
        anchor_overlap=anchor_overlap,
    )


def _tokens(text: str) -> tuple[str, ...]:
    # ``re.\w`` splits several Indic scripts at combining marks. Build tokens
    # from Unicode letter/number/mark categories so Hindi and other scripts stay
    # intact without adding a language-specific tokenizer dependency.
    values: list[str] = []
    buffer: list[str] = []
    for char in text.casefold():
        category = unicodedata.category(char)
        allowed = category[:1] in {"L", "N", "M"} or char in {".", "+", "_", "-"}
        if allowed:
            buffer.append(char)
            continue
        if buffer:
            token = "".join(buffer).strip("._+-")
            if (len(token) >= 2 or token.isdigit()) and token not in _STOPWORDS:
                values.append(token)
            buffer.clear()
    if buffer:
        token = "".join(buffer).strip("._+-")
        if (len(token) >= 2 or token.isdigit()) and token not in _STOPWORDS:
            values.append(token)
    return tuple(values)


def _shingles(tokens: Sequence[str], *, size: int) -> frozenset[str]:
    if len(tokens) < size:
        return frozenset()
    return frozenset(" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1))


def _entities(text: str) -> Iterable[str]:
    ignored = {
        "the", "a", "an", "in", "on", "at", "by", "after", "before", "this", "with",
        *_ENTITY_IGNORE_TERMS,
    }
    seen: set[str] = set()
    for match in _CAPITALIZED_PHRASE_PATTERN.finditer(text):
        raw = " ".join(match.group(0).split())
        pieces = [piece.strip(".,:;!?()[]{}\"'") for piece in raw.split()]
        pieces = [piece for piece in pieces if piece and piece.casefold() not in ignored]
        if not pieces:
            continue
        phrase = " ".join(pieces).casefold()
        if (
            len(phrase) >= 3
            and phrase not in seen
            and phrase not in _LOCATION_TERMS
            and phrase not in _ENTITY_IGNORE_TERMS
        ):
            seen.add(phrase)
            yield phrase
        # Also retain useful components. This prevents a sentence-boundary phrase
        # such as "Sriharikota ISRO" from hiding the shared ISRO/Sriharikota anchors.
        for piece in pieces:
            folded = piece.casefold()
            if (
                len(folded) < 3
                or folded in seen
                or folded in _LOCATION_TERMS
                or folded in _ENTITY_IGNORE_TERMS
            ):
                continue
            if piece.isupper() or piece[:1].isupper():
                seen.add(folded)
                yield folded


def _identifiers(text: str) -> Iterable[str]:
    """Yield strong identifiers and contextual numeric facts.

    Raw numbers such as ``24`` are too common to act as event identifiers.  The
    surrounding concept (``24:crew`` or ``240:nautical``) is much safer and
    still lets cross-publisher reports agree on distinctive factual anchors.
    """
    for match in _IDENTIFIER_PATTERN.finditer(text):
        value = match.group(0)
        folded = value.casefold()
        if value in {"The", "This", "After", "Before"}:
            continue
        if any(char.isdigit() for char in value) and any(char.isalpha() for char in value):
            yield folded
        elif value.upper().startswith("CVE-"):
            yield folded

    tokens = _tokens(text)
    for index, token in enumerate(tokens):
        numeric_token = any(char.isdigit() for char in token) and not any(char.isalpha() for char in token)
        if not numeric_token and token not in _NUMBER_WORDS:
            continue
        neighbours = [
            item
            for item in tokens[index + 1 : index + 3]
            if not any(char.isdigit() for char in item)
        ]
        if neighbours:
            yield f"{token}:{neighbours[0]}"
        if len(neighbours) >= 2:
            yield f"{token}:{neighbours[0]}:{neighbours[1]}"


def _locations(text: str) -> Iterable[str]:
    # Match location names on the same Unicode-aware token stream used by the
    # event matcher. Raw substring matching is unsafe for short aliases (for
    # example ``us`` must not match the letters inside ``suburbs``).
    tokens = _tokens(text)
    if not tokens:
        return
    for term in _LOCATION_TERMS:
        wanted = _tokens(term)
        if not wanted:
            continue
        size = len(wanted)
        if any(tokens[index : index + size] == wanted for index in range(len(tokens) - size + 1)):
            yield term.casefold()


def _event_types(tokens: Sequence[str]) -> Iterable[str]:
    token_set = frozenset(tokens)
    for event_type, vocabulary in _EVENT_TYPE_RULES.items():
        if token_set & vocabulary:
            yield event_type


def _event_type_compatibility(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.5
    if not left or not right:
        return 0.25
    overlap = len(left & right)
    if overlap:
        return min(1.0, 0.75 + 0.25 * overlap / min(len(left), len(right)))
    return 0.0


def _weighted_similarity(
    left_tokens: frozenset[str],
    right_tokens: frozenset[str],
    left_shingles: frozenset[str],
    right_shingles: frozenset[str],
    *,
    token_weight: float = 0.45,
    shingle_weight: float = 0.55,
) -> float:
    return token_weight * _jaccard(left_tokens, right_tokens) + shingle_weight * _jaccard(left_shingles, right_shingles)



def _containment(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _containment_similarity(
    left_tokens: frozenset[str],
    right_tokens: frozenset[str],
    left_shingles: frozenset[str],
    right_shingles: frozenset[str],
) -> float:
    return 0.65 * _containment(left_tokens, right_tokens) + 0.35 * _containment(
        left_shingles, right_shingles
    )

def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _overlap_or_unknown(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.5
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))



def _overlap_or_zero(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _anchor_overlap(
    *,
    entity_overlap: float,
    identifier_overlap: float,
    geographic_compatibility: float,
    event_type_compatibility: float,
    action_overlap: float,
    title_containment: float,
    content_containment: float,
) -> float:
    # A few strong, independent anchors are more useful than many generic words.
    # Taking the strongest three also supports follow-up headlines whose wording
    # changes while event type/location/factual anchors remain stable.
    signals = sorted(
        (
            entity_overlap,
            identifier_overlap,
            geographic_compatibility,
            event_type_compatibility,
            action_overlap,
            title_containment,
            content_containment,
        ),
        reverse=True,
    )
    return sum(signals[:3]) / 3 if signals else 0.0

def _geographic_compatibility(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.5
    if not left or not right:
        return 0.2
    left_specific = left - _BROAD_LOCATION_TERMS
    right_specific = right - _BROAD_LOCATION_TERMS
    if left_specific and right_specific and not (left_specific & right_specific):
        # Sharing only a country/large region is not enough to merge two distinct
        # incidents in different cities, states, islands, ports, etc.
        return 0.1
    return _overlap_or_unknown(left, right)


def _temporal_compatibility(left: datetime | None, right: datetime | None) -> float:
    if left is None or right is None:
        return 0.5
    left_utc = left.astimezone(UTC) if left.tzinfo else left.replace(tzinfo=UTC)
    right_utc = right.astimezone(UTC) if right.tzinfo else right.replace(tzinfo=UTC)
    days = abs((left_utc - right_utc).total_seconds()) / 86_400
    if days <= 1:
        return 1.0
    if days <= 3:
        return 0.85
    if days <= 7:
        return 0.65
    if days <= 14:
        return 0.4
    if days <= 30:
        return 0.2
    return 0.05


def top_terms(text: str, *, limit: int = 12) -> tuple[str, ...]:
    counts = Counter(_tokens(text))
    return tuple(term for term, _count in counts.most_common(limit))
