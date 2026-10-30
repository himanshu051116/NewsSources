from newsintel.domain.intelligence.search_stopping import (
    SearchDecision,
    SearchRoundObservation,
    assess_evidence_search_stopping,
)


def test_stops_when_required_classes_and_independence_are_satisfied():
    result = assess_evidence_search_stopping(
        ("court_record",),
        (
            SearchRoundObservation(1, 2, 3, 2, 1, ("court_record",)),
        ),
        independent_lineages=2,
        primary_records=1,
    )
    assert result.decision is SearchDecision.STOP_SUFFICIENT
    assert result.completeness_score == 1.0


def test_unresolved_primary_conflict_escalates_instead_of_more_blind_search():
    result = assess_evidence_search_stopping(
        ("official_dataset",),
        (SearchRoundObservation(1, 2, 2, 2, 1, ("official_dataset",)),),
        independent_lineages=2,
        primary_records=1,
        conflict_state="unresolved_conflict",
    )
    assert result.decision is SearchDecision.ESCALATE_CONFLICT


def test_missing_class_continues_while_budget_remains():
    result = assess_evidence_search_stopping(
        ("court_record", "official_statement"),
        (SearchRoundObservation(1, 1, 1, 1, 1, ("court_record",)),),
        independent_lineages=1,
        primary_records=1,
    )
    assert result.decision is SearchDecision.CONTINUE
    assert result.uncovered_evidence_classes == ("official_statement",)


def test_budget_exhaustion_preserves_gap():
    rounds = tuple(SearchRoundObservation(i, 1, 1, 1, 0, ()) for i in range(1, 5))
    result = assess_evidence_search_stopping(
        ("official_dataset",),
        rounds,
        independent_lineages=4,
        primary_records=0,
        max_rounds=4,
    )
    assert result.decision is SearchDecision.STOP_BUDGET
