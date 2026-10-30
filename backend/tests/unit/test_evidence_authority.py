from newsintel.domain.intelligence.authority import (
    authority_matches_source,
    normalize_domains,
    normalized_host,
)


def test_authority_match_allows_configured_subdomains_but_not_suffix_spoofing() -> None:
    allowed = ["sec.gov"]
    assert authority_matches_source(source_url="https://www.sec.gov/Archives/test", allowed_domains=allowed)
    assert authority_matches_source(source_url="https://data.sec.gov/submissions", allowed_domains=allowed)
    assert not authority_matches_source(source_url="https://sec.gov.example.com/fake", allowed_domains=allowed)


def test_domain_normalization_removes_www_and_deduplicates() -> None:
    assert normalized_host("https://www.Example.gov/path") == "example.gov"
    assert normalize_domains(["example.gov", "https://www.example.gov/x"]) == ["example.gov"]
