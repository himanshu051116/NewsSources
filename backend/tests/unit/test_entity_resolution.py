from newsintel.domain.intelligence.entities import (
    CanonicalEntityRecord,
    EntityCandidate,
    EntityType,
    canonical_entity_key,
    normalize_entity_name,
    resolve_entity,
)


def test_company_suffixes_normalize_conservatively() -> None:
    assert normalize_entity_name("Example Technologies Pvt Ltd", entity_type=EntityType.COMPANY) == "example technologies"


def test_alias_resolves_to_canonical_entity() -> None:
    key = canonical_entity_key("International Business Machines", entity_type=EntityType.COMPANY)
    record = CanonicalEntityRecord(
        entity_key=key,
        canonical_name="International Business Machines",
        entity_type=EntityType.COMPANY,
        aliases=("IBM",),
    )
    result = resolve_entity(EntityCandidate("IBM", EntityType.COMPANY), (record,))
    assert result.matched_entity_key == key
    assert result.confidence == 1.0


def test_ambiguous_name_is_not_forced_to_entity() -> None:
    records = (
        CanonicalEntityRecord("1", "National Bank", EntityType.ORGANIZATION, aliases=("NB",)),
        CanonicalEntityRecord("2", "Northern Bank", EntityType.ORGANIZATION, aliases=("NB",)),
    )
    result = resolve_entity(EntityCandidate("NB", EntityType.ORGANIZATION), records)
    assert result.matched_entity_key is None
    assert result.ambiguous is True
