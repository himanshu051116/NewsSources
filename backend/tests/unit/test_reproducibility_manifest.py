from newsintel.domain.intelligence.reproducibility import build_verification_manifest


def test_verification_manifest_is_deterministic() -> None:
    one = build_verification_manifest({"claim": {"id": "c1", "sha": "abc"}, "evidence": [{"sha": "e1"}]})
    two = build_verification_manifest({"evidence": [{"sha": "e1"}], "claim": {"sha": "abc", "id": "c1"}})
    assert one.manifest_sha256 == two.manifest_sha256
    assert len(one.manifest_sha256) == 64


def test_manifest_changes_when_evidence_changes() -> None:
    one = build_verification_manifest({"claim": "c1", "evidence": ["e1"]})
    two = build_verification_manifest({"claim": "c1", "evidence": ["e1", "e2"]})
    assert one.manifest_sha256 != two.manifest_sha256
