from newsintel.domain.intelligence.accuracy_diagnostics import DiagnosticCase, assess_accuracy_failures


def test_failure_attribution_prioritizes_observable_upstream_weaknesses():
    cases = (
        DiagnosticCase("ok", "supported", "supported", 0.9, topic_key="policy", language="en", source_key="a"),
        DiagnosticCase("extract", "supported", "contradicted", 0.9, extraction_fidelity_label="weak", topic_key="policy", language="en", source_key="a"),
        DiagnosticCase("event", "supported", "contradicted", 0.7, extraction_fidelity_label="strong", event_assignment_state="provisional", topic_key="law", language="hi", source_key="b"),
        DiagnosticCase("retrieval", "supported", "contradicted", 0.85, extraction_fidelity_label="strong", event_assignment_state="confirmed", evidence_count=0, retrieval_complete=False, topic_key="law", language="hi", source_key="b"),
        DiagnosticCase("independence", "supported", "contradicted", 0.6, extraction_fidelity_label="strong", event_assignment_state="confirmed", evidence_count=3, retrieval_complete=True, independent_lineage_count=1, primary_evidence_count=0),
        DiagnosticCase("conflict", "supported", "contradicted", 0.95, extraction_fidelity_label="strong", event_assignment_state="confirmed", evidence_count=4, retrieval_complete=True, independent_lineage_count=2, primary_evidence_count=1, unresolved_conflict=True),
        DiagnosticCase("decision", "supported", "contradicted", 0.95, extraction_fidelity_label="strong", event_assignment_state="confirmed", evidence_count=4, retrieval_complete=True, independent_lineage_count=2, primary_evidence_count=1),
    )
    result = assess_accuracy_failures(cases)
    assert result.case_count == 7
    assert result.error_count == 6
    assert result.high_confidence_error_count == 4
    assert result.taxonomy_counts == {
        "conflict_resolution": 1,
        "event_identity": 1,
        "evidence_independence": 1,
        "evidence_retrieval": 1,
        "extraction_fidelity": 1,
        "verification_decision": 1,
    }
    assert result.language_error_rates["hi"] == 1.0
    assert result.source_error_rates["a"] == 0.5
