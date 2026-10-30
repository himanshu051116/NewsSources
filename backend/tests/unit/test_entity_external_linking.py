import pytest

from newsintel.domain.intelligence.entity_linking import normalize_external_identifier


def test_wikidata_identifier_is_normalized() -> None:
    namespace, value = normalize_external_identifier("WikiData", "q42")
    assert namespace == "wikidata"
    assert value == "Q42"


def test_orcid_shape_is_validated() -> None:
    assert normalize_external_identifier("orcid", "0000-0002-1825-0097") == (
        "orcid",
        "0000-0002-1825-0097",
    )
    with pytest.raises(ValueError):
        normalize_external_identifier("orcid", "not-an-orcid")


def test_generic_identifier_rejects_whitespace_and_query_material() -> None:
    with pytest.raises(ValueError):
        normalize_external_identifier("custom", "identifier with spaces")
