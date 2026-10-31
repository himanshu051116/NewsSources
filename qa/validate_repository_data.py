"""Check repository sample/config metadata without network or external dependencies.

This is a schema and provenance check; it does not verify source URLs or story facts.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def check() -> None:
    sources = json.loads((ROOT / "config/live-source-pack.json").read_text(encoding="utf-8"))
    assert sources.get("review", {}).get("verified_live") is False
    assert sources.get("review", {}).get("rights_clearance") == "not_assessed"
    assert sources.get("sources"), "source pack must not be empty"
    seen = set()
    for source in sources["sources"]:
        assert source["name"].strip()
        assert source["name"] not in seen, "duplicate publisher entry"
        seen.add(source["name"])
        assert source["review_status"] == "manual_check_required"
        assert source.get("manual_endpoints"), "missing source endpoint"
        review = source["review_metadata"]
        assert review["source_key"] and review["publisher_group"]
        assert review["expected_language"] in {"en", "hi"}
        assert review["endpoint_kind"] in {"rss_candidate", "html_listing_candidate"}
        assert review["last_http_check_at"] is None
        assert review["last_robots_review_at"] is None
        assert review["last_terms_review_at"] is None
        assert review["retention_approved"] is False
        assert review["reviewed_by"] is None
        for address in [source["website_url"], *source["manual_endpoints"]]:
            parsed = urlsplit(address)
            assert parsed.scheme == "https" and parsed.hostname, "invalid source URL"
            assert not parsed.username and not parsed.password

    cases = json.loads(
        (ROOT / "backend/tests/fixtures/accuracy/event_pairs.json").read_text(encoding="utf-8")
    )
    assert cases, "event regression fixture must not be empty"
    unique = set()
    labels = set()
    for case in cases:
        key = case["case_key"]
        assert isinstance(key, str) and key.strip() and key not in unique, "duplicate case key"
        unique.add(key)
        assert case["case_origin"] == "constructed_regression_fixture"
        assert case["fact_verification"] == "not_performed"
        assert case["label"] in {"same", "different"}
        assert case["language"] in {"en", "hi"}
        labels.add(case["label"])
        for field in ("left_title", "left_text", "right_title", "right_text"):
            assert isinstance(case[field], str) and case[field].strip(), field
    assert labels == {"same", "different"}, "both event-link labels required"
    sample = json.loads((ROOT / "examples/editorial_review_case.json").read_text(encoding="utf-8"))
    assert sample["factual_status"] == "fictional_no_real_world_claims"
    assert sample["schema"] == "documentation_only_not_ingestible"
    notice = sample["source_notice"]
    versions = notice["versions"]
    assert [v["version"] for v in versions] == ["v1", "v2"]
    assert versions[1]["corrects"] == versions[0]["version"]
    assert versions[0]["closed_access_points"] != versions[1]["closed_access_points"]
    assert all(a["source_lineage_id"] == notice["lineage_id"] for a in sample["articles"])
    assert all(a["independent_verification"] is False for a in sample["articles"])
    assert sample["nearby_but_distinct_event"]["should_merge"] is False
    assert all(c["independent_confirmations"] == 0 for c in sample["claims"])
    print(f"Repository data OK: {len(sources['sources'])} candidate sources, {len(cases)} constructed event pairs.")
    print("Note: no live endpoints, source rights or story facts were verified.")


if __name__ == "__main__":
    check()
