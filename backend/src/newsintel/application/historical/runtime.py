from __future__ import annotations

from dataclasses import dataclass

from newsintel.adapters.historical.providers import (
    GdeltDocProvider,
    GoogleFactCheckProvider,
    GuardianProvider,
    JsonHttpTransport,
    NewsApiProvider,
    NewYorkTimesProvider,
)
from newsintel.application.historical.service import HistoricalSearchService
from newsintel.core.config import Settings


@dataclass(slots=True)
class HistoricalSearchRuntime:
    service: HistoricalSearchService
    transport: JsonHttpTransport

    async def aclose(self) -> None:
        await self.transport.aclose()


def build_historical_search_runtime(settings: Settings) -> HistoricalSearchRuntime:
    transport = JsonHttpTransport(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.historical_provider_timeout_seconds,
    )
    max_results = settings.historical_provider_max_results
    service = HistoricalSearchService(
        providers=[
            GdeltDocProvider(transport, max_results=max_results),
            GuardianProvider(
                transport,
                api_key=settings.guardian_api_key.get_secret_value(),
                max_results=max_results,
            ),
            NewYorkTimesProvider(
                transport,
                api_key=settings.new_york_times_api_key.get_secret_value(),
                max_results=min(max_results, 10),
            ),
            NewsApiProvider(
                transport,
                api_key=settings.news_api_key.get_secret_value(),
                max_results=max_results,
            ),
            GoogleFactCheckProvider(
                transport,
                api_key=settings.google_fact_check_api_key.get_secret_value(),
                max_results=min(max_results, 50),
            ),
        ],
        archive_providers=[],
        timeout_seconds=settings.historical_provider_timeout_seconds,
    )
    return HistoricalSearchRuntime(service=service, transport=transport)
