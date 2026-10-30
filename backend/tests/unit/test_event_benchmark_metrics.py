from newsintel.domain.events.benchmarking import EventLinkObservation, assess_event_link_benchmark


def test_event_benchmark_reports_false_links_and_misses_separately() -> None:
    result = assess_event_link_benchmark(
        (
            EventLinkObservation(True, True, 0.82, case_key="same-ok"),
            EventLinkObservation(True, False, 0.58, case_key="same-missed"),
            EventLinkObservation(False, False, 0.31, case_key="different-ok"),
            EventLinkObservation(False, True, 0.67, case_key="different-merged"),
        )
    )
    assert result.true_positive == 1
    assert result.false_negative == 1
    assert result.true_negative == 1
    assert result.false_positive == 1
    assert result.precision == 0.5
    assert result.recall == 0.5
    assert result.f1 == 0.5
    assert result.false_link_rate == 0.5
    assert result.false_miss_rate == 0.5
    assert set(result.failed_case_keys) == {"same-missed", "different-merged"}
