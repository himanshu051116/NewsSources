from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from newsintel.adapters.http.crawl_policy import CrawlPolicyHttpFetcher
from newsintel.adapters.http.safe_fetcher import SafeHttpFetcher
from newsintel.application.sources.dto import DiscoverPublisherCommand, FetchFrequency
from newsintel.application.sources.service import PublisherConflictError, SourceService
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.session import Database


async def seed(path: Path) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources") or []
    database = Database(settings)
    base_fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    fetcher = CrawlPolicyHttpFetcher(
        base_fetcher,
        user_agent=settings.crawler_user_agent,
        robots_enabled=settings.crawler_robots_enabled,
        robots_cache_seconds=settings.crawler_robots_cache_seconds,
        fail_closed_on_robots_error=settings.crawler_fail_closed_on_robots_error,
        max_concurrent_per_host=settings.crawler_max_concurrent_per_host,
        min_host_interval_seconds=settings.crawler_min_host_interval_seconds,
    )
    service = SourceService(session_factory=database.session_factory, fetcher=fetcher)
    failures = 0
    try:
        for source in sources:
            name = str(source.get("name") or "").strip()
            website_url = str(source.get("website_url") or "").strip()
            if not name or not website_url:
                failures += 1
                print(f"[FAIL] invalid source entry: {source!r}")
                continue
            try:
                frequency = FetchFrequency(str(source.get("fetch_frequency") or "hourly"))
                result = await service.discover_publisher(
                    DiscoverPublisherCommand(
                        publisher_name=name,
                        website_url=website_url,
                        fetch_frequency=frequency,
                        manual_endpoints=[str(item) for item in source.get("manual_endpoints") or []],
                    )
                )
                print(
                    f"[OK] {name}: publisher={result.publisher.id} "
                    f"valid_channels={result.valid_endpoint_count}"
                )
            except PublisherConflictError:
                print(f"[SKIP] {name}: already configured")
            except Exception as exc:
                failures += 1
                print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    finally:
        await database.dispose()
    return failures


def run() -> None:
    parser = argparse.ArgumentParser(description="Seed a reviewed live source pack.")
    parser.add_argument("--file", default="config/live-source-pack.json")
    args = parser.parse_args()
    failures = asyncio.run(seed(Path(args.file)))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    run()
