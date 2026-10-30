from newsintel.domain.intelligence.benchmark_corpus import BenchmarkCorpusCase, audit_benchmark_corpus


def test_corpus_audit_detects_cross_split_leakage() -> None:
    result = audit_benchmark_corpus(
        (
            BenchmarkCorpusCase("x", None, "train", "supported"),
            BenchmarkCorpusCase("x", None, "test", "supported"),
            BenchmarkCorpusCase("y", None, "test", "contradicted", adjudicator_count=2),
        )
    )
    assert "case:x" in result.leakage_keys
    assert result.readiness == "needs_review"
    assert any("leak" in warning.lower() for warning in result.warnings)


def test_corpus_audit_reports_composition() -> None:
    cases = tuple(
        BenchmarkCorpusCase(f"case-{index}", None, "test", "supported" if index % 2 else "contradicted", topic_key="technology", adjudicator_count=2)
        for index in range(30)
    )
    result = audit_benchmark_corpus(cases)
    assert result.case_count == 30
    assert result.split_counts == {"test": 30}
    assert result.topic_counts == {"technology": 30}
    assert result.readiness == "ready"
