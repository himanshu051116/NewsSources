from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class ChannelHealthInputs:
    poll_count: int
    successful_poll_count: int
    not_modified_count: int
    failure_count: int
    discovered_count: int
    admitted_count: int
    observation_count: int
    consecutive_failures: int
    last_success_at: datetime | None
    current_poll_seconds: int
    automatic_polling: bool = True


@dataclass(frozen=True, slots=True)
class ChannelHealthScore:
    score: float
    availability: float
    observation_yield: float
    recency: float
    status: str
    policy_version: str = "channel-health-v2"


def calculate_channel_health(
    inputs: ChannelHealthInputs,
    *,
    now: datetime | None = None,
) -> ChannelHealthScore:
    current_time = now or datetime.now(UTC)
    poll_count = max(0, inputs.poll_count)
    healthy_polls = max(0, inputs.successful_poll_count + inputs.not_modified_count)
    availability = 1.0 if poll_count == 0 else min(1.0, healthy_polls / poll_count)

    productive_denominator = max(1, inputs.successful_poll_count)
    observation_yield = min(1.0, max(0, inputs.observation_count) / productive_denominator)

    recency = _recency_score(
        inputs.last_success_at,
        current_poll_seconds=max(1, inputs.current_poll_seconds),
        now=current_time,
    )

    # Manual sources have no expected check cadence. Keep their factual recency
    # visible, but assess health from the checks that were explicitly requested.
    cadence_score = recency if inputs.automatic_polling else availability
    score = (0.65 * availability) + (0.20 * observation_yield) + (0.15 * cadence_score)
    if inputs.consecutive_failures > 0:
        score *= max(0.35, 1.0 - min(inputs.consecutive_failures, 5) * 0.12)
    if inputs.last_success_at is None:
        score = min(score, 0.69)
    if inputs.automatic_polling and inputs.last_success_at is not None:
        # Historical success must not hide a stopped crawler. Beyond two expected
        # intervals a channel needs attention; beyond twelve it is severely stale.
        if recency <= 0.0:
            score = min(score, 0.39)
        elif recency < 1.0:
            score = min(score, 0.69)
    score = round(max(0.0, min(1.0, score)), 4)
    return ChannelHealthScore(
        score=score,
        availability=round(availability, 4),
        observation_yield=round(observation_yield, 4),
        recency=round(recency, 4),
        status=_health_status(score, inputs.consecutive_failures),
    )


def _recency_score(
    last_success_at: datetime | None,
    *,
    current_poll_seconds: int,
    now: datetime,
) -> float:
    if last_success_at is None:
        return 0.0
    last_success = (
        last_success_at.replace(tzinfo=UTC)
        if last_success_at.tzinfo is None
        else last_success_at.astimezone(UTC)
    )
    expected = timedelta(seconds=max(current_poll_seconds * 2, 60))
    age = max(timedelta(), now - last_success)
    if age <= expected:
        return 1.0
    if age >= expected * 6:
        return 0.0
    ratio = (age - expected).total_seconds() / (expected * 5).total_seconds()
    return max(0.0, 1.0 - ratio)


def _health_status(score: float, consecutive_failures: int) -> str:
    if consecutive_failures >= 3 or score < 0.4:
        return "degraded"
    if score < 0.7:
        return "watch"
    return "healthy"
