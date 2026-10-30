from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest

from newsintel.adapters.collectors.source_discovery import (
    DiscoveredEndpoint,
    discover_syndication_directory_endpoints,
)
from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult
from newsintel.application.sources.service import SourceService
from newsintel.domain.acquisition.models import DiscoveryChannelType
from newsintel.domain.events.assignment import EventAssignmentState, decide_event_assignment
from newsintel.domain.events.matching import ArticleEventProfile, EventReference, build_event_candidates


def _fetch_result(url: str, body: bytes, *, content_type: str) -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": content_type},
        body=body,
        body_sha256=sha256(body).hexdigest(),
        retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
        redirect_chain=(),
    )


class MappingFetcher:
    def __init__(self, values: dict[str, FetchResult]) -> None:
        self.values = values
        self.requests: list[FetchRequest] = []

    async def fetch(self, request: FetchRequest) -> FetchResult:
        self.requests.append(request)
        return self.values[request.url]


def test_html_rss_directory_discovers_cross_origin_feedburner_links() -> None:
    html = b'''<html><body>
      <h1>RSS Feeds</h1>
      <a href="https://feeds.feedburner.com/example/top">Top Stories</a>
      <a href="https://feeds.feedburner.com/example/latest">Latest Stories</a>
      <a href="https://social.example/example">Follow us</a>
    </body></html>'''

    endpoints = discover_syndication_directory_endpoints(
        html,
        page_url="https://news.example/rss",
    )

    assert [item.url for item in endpoints] == [
        "https://feeds.feedburner.com/example/latest",
        "https://feeds.feedburner.com/example/top",
    ]
    assert all(item.hinted_type is DiscoveryChannelType.RSS for item in endpoints)


@pytest.mark.asyncio
async def test_endpoint_validation_expands_one_hop_html_feed_directory() -> None:
    directory_url = "https://news.example/rss"
    feed_url = "https://feeds.feedburner.com/example/top"
    directory = b'''<html><body>
      <h1>RSS Feeds</h1>
      <a href="https://feeds.feedburner.com/example/top">Top Stories</a>
    </body></html>'''
    feed = b'''<rss><channel>
      <item><title>One</title><link>https://news.example/story-one</link></item>
    </channel></rss>'''
    fetcher = MappingFetcher(
        {
            directory_url: _fetch_result(directory_url, directory, content_type="text/html"),
            feed_url: _fetch_result(feed_url, feed, content_type="application/rss+xml"),
        }
    )
    service = SourceService(session_factory=None, fetcher=fetcher)  # type: ignore[arg-type]

    validated = await service._validate_endpoints(  # noqa: SLF001 - regression test for bounded discovery
        [
            DiscoveredEndpoint(
                url=directory_url,
                source="common_path",
                hinted_type=DiscoveryChannelType.RSS,
            )
        ]
    )

    assert len(validated) == 1
    assert validated[0].url == feed_url
    assert validated[0].channel_type is DiscoveryChannelType.RSS
    assert [request.url for request in fetcher.requests] == [directory_url, feed_url]


def _ship_event_profile(*, title: str, text: str, now: datetime) -> ArticleEventProfile:
    return ArticleEventProfile(title=title, text=text, published_at=now, observed_at=now)


def test_realistic_cross_publisher_ship_sinking_pair_matches_without_lowering_threshold() -> None:
    now = datetime(2026, 8, 23, 6, 44, tzinfo=UTC)
    incoming = _ship_event_profile(
        title="Panama-flagged ship with 24 crew members sinks off Odisha coast",
        text=(
            "A Panama-flagged cargo ship sank in the Bay of Bengal on Saturday, "
            "about 240 nautical miles from the Paradip coast in Odisha. The vessel "
            "had 24 crew members."
        ),
        now=now,
    )
    reference = EventReference(
        event_id=uuid4(),
        title="Singapore-Bound Cargo Ship With 24 Crew Members Sinks Off Odisha Coast",
        text=(
            "A Panama-flagged cargo ship sank 240 nautical miles off the Odisha coast "
            "on Saturday. MV Ocean-Winner departed Paradip Port with 24 crew members "
            "aboard, bound for Singapore. The ship was carrying iron ore."
        ),
        first_detected_at=now - timedelta(hours=8),
        latest_observed_at=now - timedelta(hours=1),
    )

    candidate = build_event_candidates(incoming, [reference])[0]
    decision = decide_event_assignment([candidate])

    assert candidate.score >= 0.62
    assert decision.selected_event_id == reference.event_id
    assert decision.state in {EventAssignmentState.CANDIDATE, EventAssignmentState.CONFIRMED}


def test_similar_maritime_hijacking_is_hard_negative_for_ship_sinking_event() -> None:
    now = datetime(2026, 8, 23, 6, 44, tzinfo=UTC)
    incoming = _ship_event_profile(
        title="Panama-flagged ship with 24 crew members sinks off Odisha coast",
        text=(
            "A Panama-flagged cargo ship sank in the Bay of Bengal about 240 nautical "
            "miles from Paradip in Odisha with 24 crew members aboard."
        ),
        now=now,
    )
    unrelated = EventReference(
        event_id=uuid4(),
        title="22 Indians on board two hijacked ships near Yemen and Somalia",
        text=(
            "Two vessels were hijacked by armed pirates off Somalia and Yemen. "
            "Indian seafarers were reported safe."
        ),
        first_detected_at=now - timedelta(days=2),
        latest_observed_at=now - timedelta(days=2),
    )

    candidate = build_event_candidates(incoming, [unrelated])[0]
    decision = decide_event_assignment([candidate])

    assert candidate.score < 0.62
    assert decision.state is EventAssignmentState.PROVISIONAL
    assert decision.selected_event_id is None


def test_article_summary_projection_exists_and_surfaces_extraction_fidelity() -> None:
    from types import SimpleNamespace

    from newsintel.application.articles.query_service import _summary_from_models

    article_id = uuid4()
    event_id = uuid4()
    publisher_id = uuid4()
    version_id = uuid4()
    observed = datetime(2026, 8, 24, 1, tzinfo=UTC)
    article = SimpleNamespace(
        id=article_id,
        event_id=event_id,
        publisher_id=publisher_id,
        canonical_url="https://example.com/story",
        title="Example story",
        language="en",
        published_at=observed,
        first_observed_at=observed,
    )
    version = SimpleNamespace(
        id=version_id,
        version_number=1,
        extraction_method="json_ld_article_body",
        extraction_warnings=[],
        text_content="A sufficiently long article body for summary projection testing.",
        metadata_={
            "word_count": 10,
            "extraction_quality_score": 0.91,
            "extraction_fidelity": {
                "score": 0.97,
                "label": "strong",
                "discrepancies": [],
            },
        },
    )

    summary = _summary_from_models(article, version, None, None)

    assert summary.id == article_id
    assert summary.latest_version_id == version_id
    assert summary.latest_extraction_fidelity_score == 0.97
    assert summary.latest_extraction_fidelity_label == "strong"
