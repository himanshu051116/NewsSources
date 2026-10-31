"""Regression checks for honest fixture provenance and repository documentation."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_candidate_source_pack_is_explicitly_unverified() -> None:
    pack = json.loads((ROOT / "config/live-source-pack.json").read_text(encoding="utf-8"))
    assert pack["review"]["verified_live"] is False
    assert pack["review"]["rights_clearance"] == "not_assessed"
    assert pack["review"]["last_reviewed_at"] is None
    assert len(pack["sources"]) == len({row["name"] for row in pack["sources"]})
    assert all(row["review_status"] == "manual_check_required" for row in pack["sources"])
    reviews = [row["review_metadata"] for row in pack["sources"]]
    assert len({item["source_key"] for item in reviews}) == len(reviews)
    assert all(item["retention_approved"] is False for item in reviews)
    assert all(item["last_http_check_at"] is None for item in reviews)
    guardian = [item for item in reviews if item["publisher_group"] == "theguardian.com"]
    assert len(guardian) == 2
    sebi = next(item for item in reviews if item["source_key"] == "sebi-announcements")
    assert sebi["endpoint_kind"] == "html_listing_candidate"


def test_constructed_event_pair_labels_are_not_presented_as_fact_checks() -> None:
    cases = json.loads(
        (ROOT / "backend/tests/fixtures/accuracy/event_pairs.json").read_text(encoding="utf-8")
    )
    assert len(cases) == 20
    assert len({row["case_key"] for row in cases}) == len(cases)
    assert sum(row["label"] == "same" for row in cases) == 10
    assert sum(row["label"] == "different" for row in cases) == 10
    assert all(row["case_origin"] == "constructed_regression_fixture" for row in cases)
    assert all(row["fact_verification"] == "not_performed" for row in cases)


def test_repository_readme_and_archive_index_links_are_local_files() -> None:
    import re

    paths = [ROOT / "README.md", ROOT / "docs/archive/README.md"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            destination = path.parent / link.split("#", 1)[0]
            assert destination.is_file(), f"{path.relative_to(ROOT)}: broken link {link}"

def test_fictional_case_is_labeled_and_exposes_a_correction_without_false_corroboration() -> None:
    case = json.loads(
        (ROOT / "examples/editorial_review_case.json").read_text(encoding="utf-8")
    )
    assert case["factual_status"] == "fictional_no_real_world_claims"
    assert case["schema"] == "documentation_only_not_ingestible"
    versions = case["source_notice"]["versions"]
    assert versions[1]["corrects"] == versions[0]["version"]
    assert versions[0]["closed_access_points"] == 12
    assert versions[1]["closed_access_points"] == 9
    assert all(a["independent_verification"] is False for a in case["articles"])
    assert len({a["source_lineage_id"] for a in case["articles"]}) == 1
    assert all(c["independent_confirmations"] == 0 for c in case["claims"])
    assert case["nearby_but_distinct_event"]["should_merge"] is False
