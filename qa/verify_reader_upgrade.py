"""Read-only live quality/latency checks for the reader upgrade."""
import json
import time
from pathlib import Path

import httpx


def verify():
    evidence = {}
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=120) as client:
        client.get("/briefs").raise_for_status()
        csrf = client.cookies.get("newsintel_csrf")
        if csrf:
            client.headers["X-CSRF-Token"] = csrf
        for period in ("daily", "weekly"):
            started = time.perf_counter()
            response = client.post("/api/v1/digests/preview", json={"period":period})
            response.raise_for_status()
            edition = response.json()
            assert edition["items"]
            assert edition["word_count"] <= 360 and edition["estimated_read_seconds"] <= 120
            assert all(item["summary_available"] for item in edition["items"])
            assert all(item["report_type"] not in {"archive","opinion","service"}
                       for item in edition["items"])
            for item in edition["items"]:
                words = item["explanation"].casefold().split()
                phrases = [tuple(words[i:i+6]) for i in range(len(words)-5)]
                assert len(phrases) == len(set(phrases))
            evidence[period] = {"seconds":round(time.perf_counter()-started,3), "edition":edition}
            print(period, evidence[period]["seconds"], "seconds;",len(edition["items"]),
                  "stories;",edition["word_count"],"words;",edition["selected_publisher_count"],
                  "publishers",flush=True)
        response = client.get("/api/v1/digests/preferences")
        response.raise_for_status()
        evidence["preferences"] = response.json()
    path = Path(__file__).resolve().parents[1] / ".run/audit/reader-upgrade-live-20261028.json"
    path.write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding="utf-8")


if __name__ == "__main__":
    verify()
