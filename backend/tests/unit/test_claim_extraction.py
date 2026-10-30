from newsintel.domain.intelligence.claims import (
    CLAIM_EXTRACTOR_VERSION,
    ClaimType,
    ClaimVerificationLabel,
    claim_family_text,
    claim_sha256,
    extract_claims,
    extract_quantities,
    split_sentences,
)


def test_extract_claims_selects_factual_sentences() -> None:
    text = """
    Advertisement. ISRO launched a satellite imaging mission from Sriharikota on June 26, 2026.
    The mission will support disaster monitoring across India, officials said.
    What does this mean for investors?
    Analysts could possibly expect broader commercial demand.
    The company reported revenue rose 18% in 2026 after new contracts.
    """

    claims = extract_claims(text)

    assert CLAIM_EXTRACTOR_VERSION == "deterministic-atomic-claim-extractor-v2"
    assert len(claims) == 3
    assert claims[0].text == (
        "ISRO launched a satellite imaging mission from Sriharikota on June 26, 2026."
    )
    assert claims[0].features["has_date"] is True
    assert claims[0].features["entity_count"] >= 1
    assert all(not claim.text.endswith("?") for claim in claims)
    assert all("claim_type" in claim.features for claim in claims)
    assert all("claim_family_key" in claim.features for claim in claims)


def test_atomic_decomposition_preserves_attribution_and_separates_properties() -> None:
    claims = extract_claims(
        "The ministry said the project would cost ₹4,500 crore and would be completed by 2028."
    )

    assert [claim.text for claim in claims] == [
        "The ministry said the project would cost ₹4,500 crore.",
        "The ministry said the project would be completed by 2028.",
    ]
    assert all(claim.features["atomic_decomposition"] is True for claim in claims)
    assert claims[0].features["expected_primary_evidence"] == [
        "official_government_record",
        "gazette_or_order",
    ]


def test_quantity_normalization_distinguishes_percent_currency_and_dates() -> None:
    quantities = extract_quantities(
        "Revenue rose 18% and investment reached ₹4,500 crore in 2026."
    )

    assert quantities[0]["kind"] == "percentage"
    assert quantities[0]["normalized_value"] == 18.0
    assert quantities[1]["kind"] == "currency"
    assert quantities[1]["currency"] == "INR"
    assert quantities[1]["normalized_value"] == 45_000_000_000.0
    assert all(item["raw"] != "2026" for item in quantities)


def test_claim_family_text_groups_numeric_revisions() -> None:
    old = claim_family_text("Officials said 31 people were injured on June 5, 2026.")
    new = claim_family_text("Officials said 13 people were injured on June 6, 2026.")

    assert old == new
    assert "<NUM>" in old
    assert "<DATE>" in old


def test_claim_hash_is_normalized() -> None:
    first = claim_sha256("Company reported revenue rose 18%.")
    second = claim_sha256(" company   reported revenue rose 18%. ")

    assert first == second


def test_sentence_splitter_preserves_exact_claim_text() -> None:
    sentences = split_sentences("Company filed a case. Court approved the request.")

    assert sentences == (
        "Company filed a case.",
        "Court approved the request.",
    )


def test_claim_type_contract_contains_high_value_types() -> None:
    assert ClaimType.NUMERIC.value == "numeric"
    assert ClaimType.LEGAL.value == "legal"
    assert ClaimType.CAUSAL.value == "causal"
    assert ClaimType.PREDICTION.value == "prediction"


def test_verification_labels_match_allowed_contract() -> None:
    assert {item.value for item in ClaimVerificationLabel} == {
        "supported",
        "disputed",
        "misleading",
        "unsupported",
        "contradicted",
        "not_checkable",
    }
