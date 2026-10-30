"""Read-only live checks for short-edition quality, filtering and stable pagination."""
import json
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx


def verify():
    results = {}
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=90) as client:
        page = client.get("/briefs")
        page.raise_for_status()
        assert page.headers["cache-control"] == "private, no-store"
        csrf = client.cookies.get("newsintel_csrf")
        if csrf:
            client.headers["X-CSRF-Token"] = csrf

        def preview(**command):
            response = client.post("/api/v1/digests/preview", json=command)
            response.raise_for_status()
            return response.json()

        for period in ("daily", "weekly"):
            started = time.perf_counter()
            edition = preview(period=period)
            results[period] = edition
            results[period]["request_seconds"] = round(time.perf_counter()-started, 3)
            assert edition["items"], "Stored recent reporting should produce a readable brief"
            assert edition["word_count"] <= 360
            assert edition["estimated_read_seconds"] <= 120
            assert len(edition["items"]) <= 12
            assert len({item["article_id"] for item in edition["items"]}) == len(edition["items"])
            assert all(item["summary_available"] and item["report_type"] not in {"service", "opinion"}
                       for item in edition["items"])
            for item in edition["items"]:
                assert item["sources"] and item["explanation"]
                assert "Source text unavailable" not in item["explanation"]
                assert datetime.fromisoformat(edition["window_start"]) <= datetime.fromisoformat(
                    item["published_at"]) < datetime.fromisoformat(edition["window_end"])
            assert edition["selected_publisher_count"] == len({source["publisher_id"]
                for item in edition["items"] for source in item["sources"]})
            assert edition["selected_days"] == len({datetime.fromisoformat(
                item["published_at"]).date() for item in edition["items"]})
            print(period, {key: edition[key] for key in (
                "word_count", "selected_publisher_count", "selected_days", "unavailable_summaries",
            )}, flush=True)
            snapshot = Path(__file__).resolve().parents[1] / f".run/audit/digest-quality-{period}.json"
            snapshot.write_text(json.dumps(edition, indent=2, ensure_ascii=False), encoding="utf-8")
            first = preview(period=period, as_of=edition["window_end"],
                            full_stream=True, page_size=5)
            if first["next_offset"] is not None:
                second = preview(period=period, as_of=edition["window_end"], full_stream=True,
                                 offset=first["next_offset"], page_size=5)
                assert not ({item["article_id"] for item in first["items"]}
                            & {item["article_id"] for item in second["items"]})
            publisher_id = edition["items"][0]["sources"][0]["publisher_id"]
            filtered = preview(period=period, filters={"publisher_ids": [publisher_id]})
            assert all(source["publisher_id"] == publisher_id for item in filtered["items"]
                       for source in item["sources"])
        assert preview(filters={"keywords": ["no-match-"+uuid4().hex]})["story_count"] == 0
    return results


if __name__ == "__main__":
    result = verify()
    path = Path(__file__).resolve().parents[1] / ".run/audit/digest-quality-live.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Verified daily/weekly quality, source filters, publication windows and pagination.")
