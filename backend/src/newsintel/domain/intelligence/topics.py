from __future__ import annotations

import re
from dataclasses import dataclass

TOPIC_CLASSIFIER_VERSION = "deterministic-news-topic-v1"


@dataclass(frozen=True, slots=True)
class TopicClassification:
    topic_key: str
    score: float
    matched_terms: tuple[str, ...]
    classifier_version: str = TOPIC_CLASSIFIER_VERSION


_TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "business_finance": (
        "bank", "business", "company", "earnings", "economy", "finance", "fiscal",
        "gdp", "inflation", "investment", "market", "profit", "revenue", "stock",
    ),
    "politics_government": (
        "cabinet", "election", "government", "minister", "ministry", "parliament",
        "policy", "president", "prime minister", "senate", "vote",
    ),
    "law_justice": (
        "appeal", "court", "judge", "judgment", "lawsuit", "legal", "petition",
        "ruling", "supreme court", "tribunal", "verdict",
    ),
    "science_health": (
        "clinical", "disease", "health", "hospital", "medicine", "patient", "research",
        "scientist", "study", "trial", "vaccine",
    ),
    "technology": (
        "ai", "artificial intelligence", "chip", "cyber", "internet", "software",
        "technology", "semiconductor", "startup", "app",
    ),
    "climate_environment": (
        "climate", "emission", "environment", "flood", "heatwave", "pollution",
        "rainfall", "renewable", "temperature", "weather",
    ),
    "security_conflict": (
        "army", "attack", "conflict", "defence", "defense", "military", "missile",
        "security", "strike", "war",
    ),
    "sports": (
        "championship", "coach", "cricket", "football", "match", "olympic", "player",
        "score", "team", "tournament",
    ),
}

# Scan the article once instead of once for every term. A phrase also counts
# its contained terms, preserving the original classifier's scoring (for
# example, "supreme court" matches both "supreme court" and "court").
_ALL_TERMS = frozenset(term for terms in _TOPIC_TERMS.values() for term in terms)
_TERM_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(term)
               for term in sorted(_ALL_TERMS, key=lambda value: (-len(value), value)))
    + r")(?![a-z0-9])"
)
_CONTAINED_TERMS = {
    phrase: frozenset(term for term in _ALL_TERMS
                      if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", phrase))
    for phrase in _ALL_TERMS
}


def classify_news_topic(text: str) -> TopicClassification:
    lowered = " ".join(text.casefold().split())
    found = set().union(*(_CONTAINED_TERMS[match.group()]
                          for match in _TERM_PATTERN.finditer(lowered)))
    best_topic = "general"
    best_matches: tuple[str, ...] = ()
    best_score = 0.0
    for topic, terms in _TOPIC_TERMS.items():
        matches = tuple(term for term in terms if term in found)
        if not matches:
            continue
        # Diminishing returns prevent long keyword lists from dominating by category size.
        score = min(1.0, 0.4 + 0.18 * len(matches))
        if score > best_score or (score == best_score and topic < best_topic):
            best_topic = topic
            best_matches = matches
            best_score = score
    return TopicClassification(
        topic_key=best_topic,
        score=round(best_score if best_matches else 0.25, 4),
        matched_terms=best_matches,
    )
