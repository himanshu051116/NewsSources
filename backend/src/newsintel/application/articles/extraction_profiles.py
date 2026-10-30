from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.extractors.article_html import ExtractionProfile, ExtractedArticle
from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.models import (
    PublisherExtractionProfileModel,
    PublisherModel,
)

_ALLOWED_METHODS = {
    "auto",
    "json_ld_article_body",
    "hydration_json_body",
    "visible_text_blocks",
    "trafilatura_fallback",
}
_PARTIAL_WARNINGS = {
    "short_text_content",
    "low_extraction_quality",
    "possible_paywall_or_partial_content",
    "possible_subscription_boilerplate",
}


@dataclass(frozen=True, slots=True)
class ExtractionObservation:
    selected_method: str
    quality_score: float
    partial: bool
    candidate_quality_scores: dict[str, float]


class PublisherExtractionProfileService:
    """Resolve and conservatively learn publisher extraction preferences.

    The learned recommendation only influences method selection when the candidate
    method is nearly as good as the best extraction on the current page. It never
    bypasses crawler/access policy and never attempts subscriber-only retrieval.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(self, publisher_id: UUID) -> ExtractionProfile | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(PublisherExtractionProfileModel).where(
                    PublisherExtractionProfileModel.publisher_id == publisher_id,
                    PublisherExtractionProfileModel.enabled.is_(True),
                )
            )
            if row is None:
                return None
            return _to_profile(row)

    async def record_success(
        self,
        *,
        publisher_id: UUID,
        extracted: ExtractedArticle,
    ) -> None:
        candidate_scores = _candidate_scores(extracted.metadata.get("candidate_quality_scores"))
        observation = ExtractionObservation(
            selected_method=extracted.extraction_method,
            quality_score=_bounded_float(extracted.metadata.get("extraction_quality_score")),
            partial=bool(set(extracted.warnings) & _PARTIAL_WARNINGS),
            candidate_quality_scores=candidate_scores,
        )
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(PublisherExtractionProfileModel)
                .where(PublisherExtractionProfileModel.publisher_id == publisher_id)
                .with_for_update()
            )
            if row is None:
                publisher = await session.get(PublisherModel, publisher_id)
                if publisher is None:
                    return
                row = PublisherExtractionProfileModel(
                    id=uuid7(),
                    publisher_id=publisher_id,
                    domain=publisher.canonical_domain,
                    enabled=True,
                    preferred_method="auto",
                    recommended_method=None,
                    low_value_phrases=[],
                    skip_attribute_tokens=[],
                    skip_attribute_phrases=[],
                    paywall_or_partial_phrases=[],
                    browser_render_enabled=False,
                    browser_allowed_domains=[],
                    method_stats={},
                    sample_count=0,
                    full_success_count=0,
                    partial_success_count=0,
                    failure_count=0,
                    last_quality_score=None,
                    last_observed_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.flush()

            row.sample_count += 1
            if observation.partial:
                row.partial_success_count += 1
            else:
                row.full_success_count += 1
            row.last_quality_score = observation.quality_score
            row.last_observed_at = now
            row.method_stats = _updated_method_stats(
                row.method_stats,
                observation.candidate_quality_scores,
                selected_method=observation.selected_method,
            )
            row.recommended_method = _recommend_method(row.method_stats)
            row.updated_at = now

    async def record_failure(self, *, publisher_id: UUID) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(PublisherExtractionProfileModel)
                .where(PublisherExtractionProfileModel.publisher_id == publisher_id)
                .with_for_update()
            )
            if row is None:
                return
            row.failure_count += 1
            row.last_observed_at = now
            row.updated_at = now


def _to_profile(row: PublisherExtractionProfileModel) -> ExtractionProfile:
    preferred = row.preferred_method if row.preferred_method in _ALLOWED_METHODS else "auto"
    recommended = (
        row.recommended_method if row.recommended_method in _ALLOWED_METHODS else None
    )
    return ExtractionProfile(
        name=f"publisher:{row.publisher_id}",
        preferred_method=preferred,
        recommended_method=recommended,
        low_value_phrases=tuple(_strings(row.low_value_phrases)),
        skip_attribute_tokens=frozenset(_strings(row.skip_attribute_tokens)),
        skip_attribute_phrases=tuple(_strings(row.skip_attribute_phrases)),
        paywall_or_partial_phrases=tuple(_strings(row.paywall_or_partial_phrases)),
        browser_render_enabled=bool(row.browser_render_enabled),
        browser_allowed_domains=tuple(_strings(row.browser_allowed_domains)),
    )


def _updated_method_stats(
    current: dict[str, object] | None,
    candidate_scores: dict[str, float],
    *,
    selected_method: str,
) -> dict[str, object]:
    stats: dict[str, object] = dict(current or {})
    for method, quality in candidate_scores.items():
        if method not in _ALLOWED_METHODS or method == "auto":
            continue
        raw = stats.get(method)
        data = dict(raw) if isinstance(raw, dict) else {}
        samples = max(0, int(data.get("samples", 0))) + 1
        quality_sum = max(0.0, float(data.get("quality_sum", 0.0))) + quality
        selected = max(0, int(data.get("selected", 0))) + int(method == selected_method)
        data.update(
            {
                "samples": samples,
                "quality_sum": round(quality_sum, 6),
                "average_quality": round(quality_sum / samples, 6),
                "selected": selected,
            }
        )
        stats[method] = data
    return stats


def _recommend_method(stats: dict[str, object] | None) -> str | None:
    candidates: list[tuple[float, int, str]] = []
    for method, raw in (stats or {}).items():
        if method not in _ALLOWED_METHODS or method == "auto" or not isinstance(raw, dict):
            continue
        samples = int(raw.get("samples", 0))
        average = float(raw.get("average_quality", 0.0))
        if samples >= 5:
            candidates.append((average, samples, method))
    candidates.sort(reverse=True)
    if not candidates:
        return None
    top_average, _, top_method = candidates[0]
    second_average = candidates[1][0] if len(candidates) > 1 else 0.0
    if top_average < 0.50:
        return None
    if len(candidates) > 1 and top_average - second_average < 0.05:
        return None
    return top_method


def _candidate_scores(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, float] = {}
    for key, raw in value.items():
        method = str(key)
        if method not in _ALLOWED_METHODS:
            continue
        output[method] = _bounded_float(raw)
    return output


def _bounded_float(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = " ".join(str(item).split()).strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
