#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Sample:
    ok: bool
    status: int | None
    latency_ms: float
    error: str | None = None


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def fetch(url: str, timeout: float, authorization: str | None) -> Sample:
    headers = {"User-Agent": "NewsIntelligenceReleaseSmoke/1.0"}
    if authorization:
        headers["Authorization"] = authorization
    request = urllib.request.Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-supplied URL
            response.read(4096)
            status = int(response.status)
        latency = (time.perf_counter() - started) * 1000.0
        return Sample(ok=200 <= status < 400, status=status, latency_ms=latency)
    except urllib.error.HTTPError as exc:
        return Sample(
            ok=False,
            status=int(exc.code),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            error=type(exc).__name__,
        )
    except Exception as exc:
        return Sample(
            ok=False,
            status=None,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            error=type(exc).__name__,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded HTTP smoke/load check for a deployed News Intelligence endpoint.")
    parser.add_argument("url", help="full GET URL, for example https://host/api/v1/health/live")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--authorization", default=None, help="optional Authorization header value")
    args = parser.parse_args()
    if not 1 <= args.requests <= 100_000:
        parser.error("--requests must be between 1 and 100000")
    if not 1 <= args.concurrency <= 500:
        parser.error("--concurrency must be between 1 and 500")
    if not 0 <= args.max_error_rate <= 1:
        parser.error("--max-error-rate must be between 0 and 1")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        samples = list(
            pool.map(
                lambda _: fetch(args.url, args.timeout, args.authorization),
                range(args.requests),
            )
        )
    latencies = [item.latency_ms for item in samples]
    error_count = sum(not item.ok for item in samples)
    error_rate = error_count / len(samples)
    report = {
        "url": args.url,
        "requests": len(samples),
        "concurrency": args.concurrency,
        "successes": len(samples) - error_count,
        "errors": error_count,
        "error_rate": round(error_rate, 6),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies, default=0.0), 3),
        },
        "thresholds": {
            "max_p95_ms": args.max_p95_ms,
            "max_error_rate": args.max_error_rate,
        },
    }
    report["pass"] = bool(
        report["latency_ms"]["p95"] <= args.max_p95_ms
        and error_rate <= args.max_error_rate
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
