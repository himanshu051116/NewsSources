from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DiscoveryObservationRecord:
    candidate_id: UUID
    channel_id: UUID
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class ChannelContribution:
    channel_id: UUID
    observed_candidates: int
    unique_candidates: int
    overlap_candidates: int
    first_discovery_wins: int
    unique_contribution_rate: float
    first_discovery_rate: float


@dataclass(frozen=True, slots=True)
class DiscoveryAuditSummary:
    total_candidates: int
    single_channel_candidates: int
    multi_channel_candidates: int
    channels: tuple[ChannelContribution, ...]


def calculate_discovery_audit(
    observations: list[DiscoveryObservationRecord],
    *,
    channel_ids: list[UUID],
) -> DiscoveryAuditSummary:
    by_candidate: dict[UUID, list[DiscoveryObservationRecord]] = defaultdict(list)
    channel_candidates: dict[UUID, set[UUID]] = {channel_id: set() for channel_id in channel_ids}
    unique_counts: dict[UUID, int] = defaultdict(int)
    first_counts: dict[UUID, int] = defaultdict(int)

    for observation in observations:
        if observation.channel_id not in channel_candidates:
            continue
        by_candidate[observation.candidate_id].append(observation)
        channel_candidates[observation.channel_id].add(observation.candidate_id)

    single_channel = 0
    multi_channel = 0
    for candidate_id, candidate_observations in by_candidate.items():
        channels = {item.channel_id for item in candidate_observations}
        if len(channels) == 1:
            single_channel += 1
            unique_counts[next(iter(channels))] += 1
        else:
            multi_channel += 1
        first_at = min(item.discovered_at for item in candidate_observations)
        first_channels = {
            item.channel_id
            for item in candidate_observations
            if item.discovered_at == first_at
        }
        for channel_id in first_channels:
            first_counts[channel_id] += 1

    contributions: list[ChannelContribution] = []
    for channel_id in channel_ids:
        observed = len(channel_candidates[channel_id])
        unique = unique_counts[channel_id]
        overlap = max(0, observed - unique)
        first = first_counts[channel_id]
        contributions.append(
            ChannelContribution(
                channel_id=channel_id,
                observed_candidates=observed,
                unique_candidates=unique,
                overlap_candidates=overlap,
                first_discovery_wins=first,
                unique_contribution_rate=round(unique / observed, 4) if observed else 0.0,
                first_discovery_rate=round(first / observed, 4) if observed else 0.0,
            )
        )

    return DiscoveryAuditSummary(
        total_candidates=len(by_candidate),
        single_channel_candidates=single_channel,
        multi_channel_candidates=multi_channel,
        channels=tuple(contributions),
    )
