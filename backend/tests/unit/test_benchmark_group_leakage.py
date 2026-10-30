from newsintel.domain.intelligence.benchmark_corpus import BenchmarkCorpusCase, audit_benchmark_corpus


def test_group_and_source_document_leakage_block_readiness():
    cases = tuple(
        BenchmarkCorpusCase(
            case_key=f"c{i}",
            claim_key=None,
            split="train" if i < 20 else "test",
            adjudicated_label="supported" if i % 2 else "contradicted",
            group_key="same-event" if i in {0, 20} else f"g{i}",
            source_document_key="same-doc" if i in {1, 21} else f"d{i}",
            adjudicator_count=2,
        )
        for i in range(40)
    )
    result = audit_benchmark_corpus(cases)
    assert "same-event" in result.group_leakage_keys
    assert "same-doc" in result.source_document_leakage_keys
    assert result.readiness == "needs_review"
