from newsintel.accuracy_audit import _aggregate


def test_accuracy_audit_aggregate_separates_measured_fidelity_from_fetch_success() -> None:
    result = _aggregate(
        [
            {
                "http_status": 200,
                "ok": True,
                "fidelity": {"score": 0.95, "label": "strong", "discrepancies": []},
            },
            {
                "http_status": 200,
                "ok": True,
                "fidelity": {
                    "score": 0.7,
                    "label": "weak",
                    "discrepancies": ["headline_differs_from_publisher_metadata"],
                },
            },
            {"http_status": 503, "ok": False},
        ],
        min_fidelity=0.75,
    )
    assert result["url_count"] == 3
    assert result["http_success_count"] == 2
    assert result["extraction_success_count"] == 2
    assert result["measurable_fidelity_count"] == 2
    assert result["mean_fidelity_score"] == 0.825
    assert result["fidelity_pass_rate"] == 0.5
    assert result["top_discrepancies"][0]["name"] == "headline_differs_from_publisher_metadata"
