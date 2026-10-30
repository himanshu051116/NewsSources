from newsintel.domain.intelligence.propagation import (
    PropagationAction,
    plan_correction_propagation,
)


def test_retraction_marks_dependents_for_review_without_rewriting_verdict():
    result = plan_correction_propagation("retraction", ("c1", "c2"))
    assert result.automatic_verdict_change is False
    assert PropagationAction.INVALIDATE_SOURCE_EVIDENCE in result.impacts[0].actions
    assert PropagationAction.RECOMPUTE_RELIABILITY in result.publisher_actions


def test_normal_update_is_historical_not_automatic_invalidation():
    result = plan_correction_propagation("update", ("c1",))
    assert result.impacts[0].actions == (PropagationAction.RECORD_ONLY,)
