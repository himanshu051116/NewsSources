"""Exercise the running local feature; removes only the test stream it creates."""
import json
from pathlib import Path
from uuid import uuid4

import httpx

BASE = "http://127.0.0.1:8010"


def verify():
    results = {}
    with httpx.Client(base_url=BASE, timeout=90) as client:
        page = client.get("/briefs")
        page.raise_for_status()
        assert "Catch up in two minutes." in page.text
        assert page.headers["cache-control"] == "private, no-store"
        csrf = client.cookies.get("newsintel_csrf")
        if csrf:
            client.headers["X-CSRF-Token"] = csrf
        options = client.get("/api/v1/digests/options")
        options.raise_for_status()
        results["configured_publishers"] = len(options.json()["publishers"])

        def preview(**command):
            response = client.post("/api/v1/digests/preview", json=command)
            response.raise_for_status()
            return response.json()

        for period in ("daily", "weekly"):
            edition = preview(period=period)
            assert edition["word_count"] <= 360
            assert edition["estimated_read_seconds"] <= 120
            assert len(edition["items"]) <= 12
            results[period] = {key: edition[key] for key in (
                "story_count", "matching_reports", "publisher_count", "word_count",
                "estimated_read_seconds", "sampled", "excluded_non_reports",
            )}
            results[period]["selected_stories"] = len(edition["items"])
            if not edition["items"]:
                continue
            item = edition["items"][0]
            publisher_id = item["sources"][0]["publisher_id"]
            filtered = preview(period=period, filters={"publisher_ids": [publisher_id],
                                                       "languages": [item["language"]]})
            assert filtered["publisher_count"] == 1
            assert all(i["language"] == item["language"] for i in filtered["items"])
            full = preview(period=period, as_of=edition["window_end"], full_stream=True,
                           page_size=2)
            if full["next_offset"] is not None:
                following = preview(period=period, as_of=edition["window_end"], full_stream=True,
                                    page_size=2, offset=full["next_offset"])
                assert not ({i["article_id"] for i in full["items"]}
                            & {i["article_id"] for i in following["items"]})
        assert preview(filters={"keywords": ["no-match-" + uuid4().hex]})["story_count"] == 0
        before = client.get("/api/v1/digest-streams").json()
        saved_id = None
        try:
            created = client.post("/api/v1/digest-streams", json={
                "name": "QA disposable digest " + uuid4().hex[:8], "period": "weekly",
                "filters": {"keywords": ["cricket"]},
            })
            created.raise_for_status()
            assert created.status_code == 201
            saved_id = created.json()["id"]
            saved = client.get("/api/v1/digest-streams")
            saved.raise_for_status()
            assert any(s["id"] == saved_id for s in saved.json())
            updated = client.put(f"/api/v1/digest-streams/{saved_id}", json={
                "name": "QA updated disposable digest", "period": "daily",
                "filters": {"topics": ["technology"]},
            })
            updated.raise_for_status()
            assert updated.json()["period"] == "daily"
            assert client.put(f"/api/v1/digest-streams/{uuid4()}",
                              json={"name": "Missing"}).status_code == 404
        finally:
            if saved_id:
                deleted = client.delete(f"/api/v1/digest-streams/{saved_id}")
                assert deleted.status_code == 204, deleted.text
        after = client.get("/api/v1/digest-streams")
        after.raise_for_status()
        assert {s["id"] for s in before} == {s["id"] for s in after.json()}
        results["saved_stream_roundtrip"] = (
            "created, reloaded, updated, deleted; existing streams preserved"
        )
    return results


if __name__ == "__main__":
    result = verify()
    output = Path(__file__).resolve().parents[1] / ".run" / "audit" / "digests-live.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
