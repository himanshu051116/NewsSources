from datetime import UTC, datetime, timedelta

from newsintel.application.sources.audit import (
    DiscoveryObservationRecord,
    calculate_discovery_audit,
)
from newsintel.core.ids import uuid7


def test_discovery_audit_measures_unique_and_first_contribution() -> None:
    rss = uuid7()
    sitemap = uuid7()
    a = uuid7()
    b = uuid7()
    c = uuid7()
    now = datetime(2026, 8, 13, 1, 0, tzinfo=UTC)
    observations = [
        DiscoveryObservationRecord(a, rss, now),
        DiscoveryObservationRecord(a, sitemap, now + timedelta(seconds=20)),
        DiscoveryObservationRecord(b, rss, now),
        DiscoveryObservationRecord(c, sitemap, now),
    ]

    audit = calculate_discovery_audit(observations, channel_ids=[rss, sitemap])
    by_channel = {item.channel_id: item for item in audit.channels}

    assert audit.total_candidates == 3
    assert audit.single_channel_candidates == 2
    assert audit.multi_channel_candidates == 1
    assert by_channel[rss].unique_candidates == 1
    assert by_channel[rss].first_discovery_wins == 2
    assert by_channel[sitemap].unique_candidates == 1
    assert by_channel[sitemap].first_discovery_wins == 1
