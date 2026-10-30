from newsintel.domain.intelligence.adjudication import (
    AdjudicationReview,
    assess_adjudication_agreement,
    decide_consensus,
)


def test_agreement_and_consensus_for_unanimous_double_review():
    reviews = (
        AdjudicationReview("c1", "r1", "supported"),
        AdjudicationReview("c1", "r2", "supported"),
        AdjudicationReview("c2", "r1", "contradicted"),
        AdjudicationReview("c2", "r2", "supported"),
    )
    result = assess_adjudication_agreement(reviews)
    assert result.case_count == 2
    assert result.multi_review_case_count == 2
    assert result.unanimous_case_count == 1
    assert result.disagreement_case_count == 1
    assert result.pairwise_agreement == 0.5
    assert result.krippendorff_alpha_nominal is not None
    decision = decide_consensus("c1", reviews)
    assert decision.state == "consensus"
    assert decision.label == "supported"


def test_disagreement_requires_separate_adjudicator():
    reviews = (
        AdjudicationReview("c1", "r1", "supported"),
        AdjudicationReview("c1", "r2", "contradicted"),
    )
    decision = decide_consensus("c1", reviews)
    assert decision.state == "disagreement"
    assert decision.label is None

    adjudicated = reviews + (AdjudicationReview("c1", "a1", "supported", "adjudicator"),)
    decision = decide_consensus("c1", adjudicated)
    assert decision.state == "adjudicated"
    assert decision.label == "supported"
    agreement = assess_adjudication_agreement(adjudicated)
    assert agreement.adjudicated_disagreement_count == 1


def test_insufficient_reviews_do_not_finalize():
    reviews = (AdjudicationReview("c1", "r1", "supported"),)
    result = decide_consensus("c1", reviews)
    assert result.state == "insufficient_reviews"
    assert result.label is None


def test_blind_review_rows_do_not_expose_model_prediction():
    from types import SimpleNamespace
    from uuid import uuid4
    from newsintel.benchmark_dataset import _blind_review_row

    candidate = SimpleNamespace(
        id=uuid4(),
        case_key="claim:abc",
        language="en",
        topic_key="policy",
        predicted_label="supported",
        predicted_confidence=0.99,
        source_snapshot={"article_title": "Example", "source_url": "https://example.com/a", "claim_text": "A claim"},
    )
    row = _blind_review_row(candidate)
    assert "predicted_label" not in row
    assert "predicted_confidence" not in row
    assert row["claim_text"] == "A claim"
