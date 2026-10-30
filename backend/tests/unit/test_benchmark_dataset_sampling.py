from newsintel.benchmark_dataset import _balanced


def test_balanced_benchmark_sampling_round_robins_prediction_labels() -> None:
    rows = [
        {"predicted_label": "supported", "id": "s1"},
        {"predicted_label": "supported", "id": "s2"},
        {"predicted_label": "supported", "id": "s3"},
        {"predicted_label": "contradicted", "id": "c1"},
        {"predicted_label": "not_checkable", "id": "n1"},
    ]
    sampled = _balanced(rows, 4)
    assert len(sampled) == 4
    assert {item["predicted_label"] for item in sampled[:3]} == {
        "supported",
        "contradicted",
        "not_checkable",
    }
