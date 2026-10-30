from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from newsintel.application.sources.health import ChannelHealthInputs, calculate_channel_health


def test_healthy_channel_scores_high() -> None:
    now = datetime(2026, 8, 13, 1, 0, tzinfo=UTC)
    result = calculate_channel_health(
        ChannelHealthInputs(
            poll_count=10,
            successful_poll_count=6,
            not_modified_count=4,
            failure_count=0,
            discovered_count=40,
            admitted_count=20,
            observation_count=20,
            consecutive_failures=0,
            last_success_at=now - timedelta(minutes=2),
            current_poll_seconds=300,
        ),
        now=now,
    )

    assert result.status == "healthy"
    assert result.score >= 0.9


def test_repeated_failures_degrade_channel_health() -> None:
    now = datetime(2026, 8, 13, 1, 0, tzinfo=UTC)
    result = calculate_channel_health(
        ChannelHealthInputs(
            poll_count=10,
            successful_poll_count=4,
            not_modified_count=0,
            failure_count=6,
            discovered_count=2,
            admitted_count=1,
            observation_count=1,
            consecutive_failures=4,
            last_success_at=now - timedelta(hours=6),
            current_poll_seconds=300,
        ),
        now=now,
    )

    assert result.status == "degraded"
    assert result.score < 0.4


def successful_inputs(now: datetime) -> ChannelHealthInputs:
    return ChannelHealthInputs(
        poll_count=12, successful_poll_count=12, not_modified_count=0, failure_count=0,
        discovered_count=120, admitted_count=120, observation_count=120,
        consecutive_failures=0, last_success_at=now, current_poll_seconds=300,
    )


@pytest.mark.parametrize(("minutes", "status"), [(5, "healthy"), (11, "watch"), (61, "degraded")])
def test_successful_history_cannot_hide_an_overdue_automatic_source(minutes, status):
    now = datetime(2026, 10, 27, tzinfo=UTC)
    inputs = replace(successful_inputs(now), last_success_at=now - timedelta(minutes=minutes))
    assert calculate_channel_health(inputs, now=now).status == status


def test_manual_source_is_not_penalized_for_age_alone():
    now = datetime(2026, 10, 27, tzinfo=UTC)
    inputs = replace(successful_inputs(now), last_success_at=now - timedelta(days=30),
                     automatic_polling=False)
    result = calculate_channel_health(inputs, now=now)
    assert result.status == "healthy"
    assert result.score == 1.0
    assert result.recency == 0.0
    assert calculate_channel_health(replace(inputs, consecutive_failures=3), now=now).status == "degraded"


@pytest.mark.parametrize("automatic_polling", [True, False])
def test_never_polled_source_does_not_claim_healthy_or_a_missed_schedule(automatic_polling):
    now = datetime(2026, 10, 27, tzinfo=UTC)
    inputs = replace(successful_inputs(now), last_success_at=None, poll_count=0,
                     successful_poll_count=0, observation_count=0, admitted_count=0,
                     discovered_count=0, automatic_polling=automatic_polling)
    assert calculate_channel_health(inputs, now=now).status == "watch"
