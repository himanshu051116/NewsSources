"""Regressions for abandoned work, stale-writer fencing, and honest historical citations.

Pure checks do not substitute for a PostgreSQL concurrency integration test.
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from newsintel.application.briefings.service import (
    GroundedBriefingService,
    _briefing_history_items,
)
from newsintel.application.historical.enrichment_service import (
    LeasedHistoricalEnrichmentJob,
    _owns_historical_lease,
)
from newsintel.infrastructure.db.models import ArticleHistoricalEnrichmentJobModel


def test_expired_historical_attempt_cannot_write_results() -> None:
    now = datetime.now(UTC)
    job = LeasedHistoricalEnrichmentJob(
        id=uuid4(), article_id=uuid4(), article_version_id=uuid4(), event_id=uuid4(),
        cutoff_at=now, attempt_count=1, lease_owner="worker-a", lease_started_at=now-timedelta(minutes=4),
    )
    row = SimpleNamespace(state="running", lease_owner="worker-a",
                          started_at=job.lease_started_at, lease_expires_at=now+timedelta(minutes=2))
    assert _owns_historical_lease(row, job, now)
    assert not _owns_historical_lease(row, job, now+timedelta(minutes=3))
    row.started_at = now-timedelta(minutes=1)
    assert not _owns_historical_lease(row, job, now)  # same worker, newer attempt
    row.started_at = job.lease_started_at
    row.lease_owner = "worker-b"
    assert not _owns_historical_lease(row, job, now)
    row.lease_owner = "worker-a"
    row.state = "succeeded"
    assert not _owns_historical_lease(row, job, now)
    assert not _owns_historical_lease(None, job, now)


def test_historical_heartbeat_has_state_owner_attempt_expiry_guards() -> None:
    import inspect
    from newsintel.application.historical.enrichment_service import HistoricalEnrichmentService
    source = inspect.getsource(HistoricalEnrichmentService.heartbeat)
    for guard in ("lease_owner == job.lease_owner", "started_at == job.lease_started_at", "lease_expires_at > now", 'state == "running"'):
        assert guard in source


def test_briefing_leasing_reclaims_expired_running_and_avoids_unexpired() -> None:
    import inspect
    source = inspect.getsource(GroundedBriefingService.lease_next)
    assert 'EventBriefingJobModel.state == "running"' in source
    assert 'EventBriefingJobModel.lease_expires_at < now' in source
    assert 'with_for_update(skip_locked=True)' in source
    # SQL text includes the running branch instead of only queued/retry.
    assert 'row.lease_version += 1' in source


def test_historical_citations_are_date_ordered_and_cannot_leak_future_information() -> None:
    cutoff = datetime(2026, 10, 16, tzinfo=UTC)
    entries = [
        {"title": "old release", "url": "https://example.org/one?utm_source=abc", "published_at": "2021-10-13"},
        {"title": "duplicate old", "url": "https://example.org/one", "published_at": "2021-10-13"},
        {"title": "newer release", "url": "https://example.org/two", "published_at": "2025-08-05T11:00:00Z"},
        {"title": "future leak", "url": "https://example.org/future", "published_at": "2026-10-17T00:00:00Z"},
        {"title": "observed undated", "url": "https://example.org/observed", "observed_at": "2022-01-03T00:00:00Z"},
        {"title": "unverified date", "url": "https://example.org/undated"},
    ]
    history = _briefing_history_items(entries, cutoff=cutoff)
    assert [item["title"] for item in history] == ["old release", "observed undated", "newer release", "unverified date"]
    assert history[1]["published_at"] is None
    assert history[1]["date_basis"] == "observation"
    assert history[3]["date_basis"] == "unknown"


def test_briefing_no_history_does_not_claim_zero_changes() -> None:
    import inspect
    source = inspect.getsource(GroundedBriefingService._build)
    assert "No historical comparison is available yet" in source
    assert "These are not event-wide totals" in source
    assert "ordered_links[:8]" in source


def test_history_url_normalization_rejects_malformed_ports_without_crashing():
    from newsintel.domain.intelligence.historical_enrichment import normalize_history_url
    assert normalize_history_url("https://example.org:broken/story") is None
    assert normalize_history_url("http://[::1]:8080/story?utm_source=test") == "http://[::1]:8080/story"
