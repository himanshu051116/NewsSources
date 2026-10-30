from newsintel.domain.intelligence.lineage import (
    estimate_lineage_similarity,
    fingerprint_content,
    fingerprint_metadata,
)


def test_exact_republication_has_same_lineage_signature() -> None:
    left = fingerprint_content("The ministry released the report. Revenue rose 18 percent.")
    right = fingerprint_content("The ministry released the report. Revenue rose 18 percent.")

    assert left.exact_signature == right.exact_signature
    assert estimate_lineage_similarity(left, right) == 1.0


def test_different_content_does_not_look_exactly_syndicated() -> None:
    left = fingerprint_content("Alpha beta gamma delta epsilon zeta eta theta iota kappa.")
    right = fingerprint_content("Market prices fell sharply after a separate policy announcement.")

    assert left.exact_signature != right.exact_signature
    assert estimate_lineage_similarity(left, right) < 0.5


def test_lineage_metadata_is_json_serializable_shape() -> None:
    metadata = fingerprint_metadata(fingerprint_content("one two three four five six seven"))

    assert metadata["version"] == "content-lineage-minhash-v1"
    assert isinstance(metadata["minhash"], list)
    assert all(isinstance(item, str) for item in metadata["minhash"])


def test_near_republication_retains_high_similarity() -> None:
    base = (
        "The ministry released the annual report on Tuesday. Revenue rose 18 percent "
        "after export demand increased. Officials said the programme would continue "
        "through next year and additional regional offices would open."
    )
    edited = base + " The statement was published online."

    score = estimate_lineage_similarity(fingerprint_content(base), fingerprint_content(edited))

    assert score >= 0.6


def test_lineage_similarity_caps_independence_without_changing_stance() -> None:
    from newsintel.domain.intelligence.lineage import independence_cap_from_lineage_similarity

    assert independence_cap_from_lineage_similarity(1.0) == 0.05
    assert independence_cap_from_lineage_similarity(0.9) == 0.2
    assert independence_cap_from_lineage_similarity(0.75) == 0.5
    assert independence_cap_from_lineage_similarity(0.4) == 1.0


def test_lineage_fingerprint_round_trips_from_metadata() -> None:
    from newsintel.domain.intelligence.lineage import fingerprint_from_metadata

    original = fingerprint_content("one two three four five six seven eight nine")
    recovered = fingerprint_from_metadata(fingerprint_metadata(original))
    assert recovered is not None
    assert recovered.exact_signature == original.exact_signature
    assert recovered.minhash == original.minhash
