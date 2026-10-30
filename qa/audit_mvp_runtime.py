"""Read-only runtime evidence for the reader MVP; never resets or seeds data."""
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


def audit():
    evidence = {"checked_at": datetime.now(UTC).isoformat(), "requests": []}
    path = Path(__file__).resolve().parents[1] / ".run/audit/mvp-runtime-20261027.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=120) as client:
        def check(method, route, **kwargs):
            start = time.perf_counter()
            response = client.request(method, route, **kwargs)
            item = {"method": method, "route": route, "status": response.status_code,
                    "seconds": round(time.perf_counter() - start, 3)}
            if "application/json" in response.headers.get("content-type", ""):
                item["data"] = response.json()
            evidence["requests"].append(item)
            path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            print({key: value for key, value in item.items() if key != "data"}, flush=True)
            csrf = client.cookies.get("newsintel_csrf")
            if csrf:
                client.headers["X-CSRF-Token"] = csrf
            return response

        for route in ("/api/v1/health/live", "/api/v1/health/ready", "/briefs",
                      "/app", "/news", "/news-sources", "/api/v1/status",
                      "/api/v1/publishers", "/api/v1/digests/options",
                      "/api/v1/digest-streams", "/api/v1/articles?limit=10",
                      "/api/v1/events?limit=10"):
            check("GET", route)
        for period in ("daily", "weekly"):
            response = check("POST", "/api/v1/digests/preview", json={"period": period})
            if response.status_code != 200:
                continue
            edition = response.json()
            print({"period": period, "stories": len(edition["items"]),
                   "matching": edition["story_count"], "words": edition["word_count"],
                   "publishers": edition["selected_publisher_count"],
                   "capture": edition["latest_capture_at"]}, flush=True)
            assert edition["word_count"] <= 360
            assert edition["estimated_read_seconds"] <= 120
            assert len(edition["items"]) <= 12
            first = check("POST", "/api/v1/digests/preview", json={
                "period": period, "as_of": edition["window_end"],
                "full_stream": True, "page_size": 5}).json()
            if first.get("next_offset") is not None:
                second = check("POST", "/api/v1/digests/preview", json={
                    "period": period, "as_of": edition["window_end"], "full_stream": True,
                    "page_size": 5, "offset": first["next_offset"]}).json()
                assert not ({item["article_id"] for item in first["items"]}
                            & {item["article_id"] for item in second["items"]})
        check("POST", "/api/v1/digests/preview", json={"period": "monthly"})
    return evidence


if __name__ == "__main__":
    audit()
