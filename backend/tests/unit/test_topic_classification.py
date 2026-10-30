import re

from newsintel.domain.intelligence.topics import _TOPIC_TERMS, classify_news_topic


def test_topic_classifier_prefers_business_for_financial_claims() -> None:
    result = classify_news_topic("The company reported higher revenue and profit after earnings.")
    assert result.topic_key == "business_finance"
    assert "revenue" in result.matched_terms


def test_topic_classifier_returns_general_when_no_subject_signal_exists() -> None:
    assert classify_news_topic("A local event happened on Tuesday.").topic_key == "general"


def test_combined_scan_preserves_original_term_boundaries_phrases_and_scores() -> None:
    terms = sorted({term for values in _TOPIC_TERMS.values() for term in values})
    examples = ["The supreme court hears prime minister's appeal.",
                "Artificial intelligence app targets hospital study.",
                "SCORECARD healthcare chairman teams newsletter", "संसद bank नीति"]
    examples += [f"{term}; x{term} {term}2 pre-{term} post_{term}" for term in terms]
    examples += [" ".join(terms), " ".join(reversed(terms))]
    for text in examples:
        lowered = " ".join(text.casefold().split())
        expected = []
        for topic, candidates in _TOPIC_TERMS.items():
            matches = tuple(term for term in candidates
                            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered))
            if matches:
                expected.append((-min(1.0, 0.4+0.18*len(matches)), topic, matches))
        actual = classify_news_topic(text)
        if expected:
            score, topic, matches = min(expected)
            assert (actual.topic_key, actual.score, actual.matched_terms) == (
                topic, round(-score, 4), matches,
            )
        else:
            assert (actual.topic_key, actual.score, actual.matched_terms) == ("general", .25, ())
