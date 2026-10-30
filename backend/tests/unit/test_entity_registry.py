from newsintel.domain.intelligence.entity_registry import (
    EntityDescriptor,
    EntityLinkState,
    RegistryCandidate,
    resolve_registry_candidates,
)


def test_registry_linker_matches_identity_with_type_and_country():
    result = resolve_registry_candidates(
        EntityDescriptor("Reserve Bank of India", "organization", ("RBI",), "India"),
        (
            RegistryCandidate("Q1", "Reserve Bank of India", "organization", ("RBI",), "India"),
            RegistryCandidate("Q2", "Reserve Bank", "organization", (), "Australia"),
        ),
    )
    assert result.state is EntityLinkState.MATCHED
    assert result.selected is not None and result.selected.external_id == "Q1"


def test_registry_linker_refuses_close_ambiguous_candidates():
    result = resolve_registry_candidates(
        EntityDescriptor("John Smith", "person"),
        (
            RegistryCandidate("1", "John Smith", "person"),
            RegistryCandidate("2", "John Smith", "person"),
        ),
    )
    assert result.state is EntityLinkState.AMBIGUOUS
    assert result.selected is None
