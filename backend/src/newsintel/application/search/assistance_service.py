from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.search.assistance_dto import (
    SearchAssistanceSuggestionView,
    SearchAssistanceView,
)
from newsintel.domain.search.query_language import (
    detect_script,
    language_filter_hint,
    normalize_query,
)
from newsintel.infrastructure.db.models import (
    CanonicalEntityModel,
    EntityAliasModel,
    EventModel,
    PublisherModel,
)


class SearchAssistanceService:
    """Precision-first, suggestion-only query assistance.

    The service intentionally avoids opaque query rewriting. It uses approved
    entity aliases and a bounded vocabulary of active publishers/recent events
    to offer explicit corrections or canonical-name suggestions.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def suggest(
        self,
        query: str,
        *,
        limit: int = 6,
        include_entities: bool = False,
    ) -> SearchAssistanceView:
        normalized = normalize_query(query)
        script = detect_script(normalized)
        if len(normalized) < 2:
            return SearchAssistanceView(
                query=query,
                normalized_query=normalized,
                script=script,
                language_filter_hint=language_filter_hint(script),
                suggestions=[],
            )

        async with self._session_factory() as session:
            entities = []
            aliases = []
            if include_entities:
                entities = list(
                    (
                        await session.execute(
                            select(
                                CanonicalEntityModel.canonical_name,
                                CanonicalEntityModel.entity_type,
                            )
                            .where(CanonicalEntityModel.resolution_status == "active")
                            .order_by(CanonicalEntityModel.updated_at.desc())
                            .limit(300)
                        )
                    ).all()
                )
                aliases = list(
                    (
                        await session.execute(
                            select(
                                EntityAliasModel.alias,
                                CanonicalEntityModel.canonical_name,
                                CanonicalEntityModel.entity_type,
                                EntityAliasModel.language,
                            )
                            .join(CanonicalEntityModel, CanonicalEntityModel.id == EntityAliasModel.entity_id)
                            .where(CanonicalEntityModel.resolution_status == "active")
                            .order_by(EntityAliasModel.created_at.desc())
                            .limit(500)
                        )
                    ).all()
                )
            publishers = list(
                (
                    await session.execute(
                        select(PublisherModel.name, PublisherModel.slug)
                        .where(PublisherModel.active.is_(True))
                        .order_by(PublisherModel.updated_at.desc())
                        .limit(250)
                    )
                ).all()
            )
            events = list(
                (
                    await session.execute(
                        select(EventModel.title, EventModel.lifecycle_status)
                        .order_by(EventModel.last_material_change_at.desc())
                        .limit(350)
                    )
                ).all()
            )

        suggestions: list[SearchAssistanceSuggestionView] = []
        query_key = normalized.casefold()
        if normalized != query.strip():
            suggestions.append(
                SearchAssistanceSuggestionView(
                    kind="normalized",
                    replacement=normalized,
                    label=normalized,
                    reason="Unicode/whitespace normalization only; lexical intent is unchanged.",
                    score=1.0,
                )
            )

        # Approved alias expansion is identity-grounded and should outrank fuzzy spelling help.
        for alias, canonical_name, entity_type, alias_language in aliases:
            if normalize_query(alias).casefold() == query_key and normalize_query(canonical_name).casefold() != query_key:
                suggestions.append(
                    SearchAssistanceSuggestionView(
                        kind="approved_alias",
                        replacement=canonical_name,
                        label=canonical_name,
                        reason=f"Approved alias '{alias}' maps to this canonical entity.",
                        score=1.0,
                        metadata={"entity_type": entity_type, "alias_language": alias_language},
                    )
                )

        candidates: list[tuple[str, str, dict[str, object]]] = []
        candidates.extend(
            (name, "canonical_entity", {"entity_type": entity_type})
            for name, entity_type in entities
        )
        candidates.extend(
            (
                alias,
                "entity_alias",
                {
                    "canonical_name": canonical_name,
                    "entity_type": entity_type,
                    "language": alias_language,
                },
            )
            for alias, canonical_name, entity_type, alias_language in aliases
        )
        candidates.extend((name, "publisher", {"slug": slug}) for name, slug in publishers)
        candidates.extend((title, "event_title", {"lifecycle_status": lifecycle}) for title, lifecycle in events)

        for candidate, kind, metadata in candidates:
            candidate_norm = normalize_query(candidate)
            candidate_key = candidate_norm.casefold()
            if not candidate_norm or candidate_key == query_key:
                continue
            candidate_script = detect_script(candidate_norm)
            if script not in {"unknown", "mixed"} and candidate_script not in {script, "unknown", "mixed"}:
                continue
            score = _similarity(query_key, candidate_key)
            threshold = 0.80 if len(query_key) < 6 else 0.72
            if score < threshold:
                continue
            replacement = str(metadata.get("canonical_name") or candidate_norm) if kind == "entity_alias" else candidate_norm
            reason = {
                "canonical_entity": "Close match to an active canonical entity name.",
                "entity_alias": f"Close match to an approved alias for {metadata.get('canonical_name') or candidate_norm}.",
                "publisher": "Close match to an active publisher name.",
                "event_title": "Close match to a recently active event title.",
            }.get(kind, "Close corpus vocabulary match.")
            suggestions.append(
                SearchAssistanceSuggestionView(
                    kind=kind,
                    replacement=replacement,
                    label=replacement,
                    reason=reason,
                    score=round(score, 4),
                    metadata=metadata,
                )
            )

        ordered: list[SearchAssistanceSuggestionView] = []
        seen: set[str] = set()
        for item in sorted(suggestions, key=lambda value: (-value.score, value.kind, value.label.casefold())):
            key = normalize_query(item.replacement).casefold()
            if not key or key == query_key or key in seen:
                continue
            seen.add(key)
            ordered.append(item)
            if len(ordered) >= max(1, min(limit, 12)):
                break

        return SearchAssistanceView(
            query=query,
            normalized_query=normalized,
            script=script,
            language_filter_hint=language_filter_hint(script),
            suggestions=ordered,
        )


def _similarity(left: str, right: str) -> float:
    direct = SequenceMatcher(None, left, right).ratio()
    left_tokens = " ".join(sorted(left.split()))
    right_tokens = " ".join(sorted(right.split()))
    token_order_independent = SequenceMatcher(None, left_tokens, right_tokens).ratio()
    return max(direct, token_order_independent)
