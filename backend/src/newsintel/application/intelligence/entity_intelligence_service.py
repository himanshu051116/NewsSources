from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Integer, String, bindparam, delete, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from newsintel.application.intelligence.entity_intelligence_dto import (
    EntityAliasSummaryView,
    EntityExternalIdSummaryView,
    EntityMentionRefreshView,
    EntityMentionView,
    EntityProfileView,
    EntitySearchResultView,
    EntitySearchView,
)
from newsintel.domain.intelligence.entities import EntityType, normalize_entity_name
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleModel,
    ArticleVersionModel,
    CanonicalEntityModel,
    EntityAliasModel,
    EntityExternalIdentifierModel,
    EntityMentionModel,
    EventModel,
    PublisherModel,
)


_ENTITY_SEARCH_SQL = r"""
WITH search_input AS (
    SELECT websearch_to_tsquery('simple', :query) AS tsq
), alias_rank AS (
    SELECT
        a.entity_id,
        max(ts_rank_cd(to_tsvector('simple', coalesce(a.alias, '')), s.tsq)) AS alias_score,
        (array_agg(a.alias ORDER BY ts_rank_cd(to_tsvector('simple', coalesce(a.alias, '')), s.tsq) DESC, a.alias))[1] AS matched_alias,
        count(*)::int AS alias_count
    FROM entity_aliases a
    CROSS JOIN search_input s
    WHERE to_tsvector('simple', coalesce(a.alias, '')) @@ s.tsq
    GROUP BY a.entity_id
)
SELECT
    e.id,
    e.canonical_name,
    e.entity_type,
    e.country_code,
    greatest(
        ts_rank_cd(to_tsvector('simple', coalesce(e.canonical_name, '')), s.tsq),
        coalesce(ar.alias_score, 0)
    )::double precision AS score,
    CASE
        WHEN ar.alias_score IS NOT NULL
             AND ar.alias_score > ts_rank_cd(to_tsvector('simple', coalesce(e.canonical_name, '')), s.tsq)
        THEN ar.matched_alias
        ELSE NULL
    END AS matched_alias,
    coalesce((SELECT count(*)::int FROM entity_aliases ea WHERE ea.entity_id = e.id), 0) AS alias_count
FROM canonical_entities e
CROSS JOIN search_input s
LEFT JOIN alias_rank ar ON ar.entity_id = e.id
WHERE (
    to_tsvector('simple', coalesce(e.canonical_name, '')) @@ s.tsq
    OR ar.entity_id IS NOT NULL
)
AND coalesce(e.resolution_status, 'active') = 'active'
AND (:entity_type IS NULL OR e.entity_type = :entity_type)
AND (:country_code IS NULL OR e.country_code = :country_code)
ORDER BY score DESC, e.canonical_name ASC, e.id ASC
LIMIT :limit
"""

_ENTITY_SEARCH_QUERY = text(_ENTITY_SEARCH_SQL).bindparams(
    bindparam("query", type_=String),
    bindparam("entity_type", type_=String),
    bindparam("country_code", type_=String),
    bindparam("limit", type_=Integer),
)


class EntityIntelligenceService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        country_code: str | None = None,
        limit: int = 30,
    ) -> EntitySearchView:
        normalized = " ".join(query.split())
        if len(normalized) < 2:
            return EntitySearchView(query=normalized, results=[], result_count=0)
        entity_type = (entity_type or "").strip().lower() or None
        if entity_type is not None and entity_type not in {item.value for item in EntityType}:
            raise ValueError(f"unsupported entity type: {entity_type}")
        country_code = (country_code or "").strip().upper() or None
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        _ENTITY_SEARCH_QUERY,
                        {
                            "query": normalized,
                            "entity_type": entity_type,
                            "country_code": country_code,
                            "limit": max(1, min(limit, 100)),
                        },
                    )
                ).mappings().all()
            )
        return EntitySearchView(
            query=normalized,
            result_count=len(rows),
            results=[
                EntitySearchResultView(
                    id=row["id"],
                    canonical_name=str(row["canonical_name"]),
                    entity_type=str(row["entity_type"]),
                    country_code=row["country_code"],
                    score=float(row["score"] or 0.0),
                    matched_alias=str(row["matched_alias"]) if row["matched_alias"] else None,
                    alias_count=int(row["alias_count"] or 0),
                )
                for row in rows
            ],
        )

    async def profile(self, entity_id: UUID, *, mention_limit: int = 50) -> EntityProfileView | None:
        async with self._session_factory() as session:
            entity = await session.get(CanonicalEntityModel, entity_id)
            if entity is None:
                return None
            aliases = list(
                (
                    await session.scalars(
                        select(EntityAliasModel)
                        .where(EntityAliasModel.entity_id == entity_id)
                        .order_by(EntityAliasModel.confidence.desc(), EntityAliasModel.alias.asc())
                    )
                ).all()
            )
            external_ids = list(
                (
                    await session.scalars(
                        select(EntityExternalIdentifierModel)
                        .where(EntityExternalIdentifierModel.entity_id == entity_id)
                        .order_by(EntityExternalIdentifierModel.namespace, EntityExternalIdentifierModel.external_id)
                    )
                ).all()
            )
            counts = (
                await session.execute(
                    select(
                        func.count(distinct(EntityMentionModel.claim_id)),
                        func.count(distinct(EntityMentionModel.article_id)),
                        func.count(distinct(ArticleModel.event_id)),
                        func.count(distinct(ArticleModel.publisher_id)),
                    )
                    .select_from(EntityMentionModel)
                    .join(ArticleModel, ArticleModel.id == EntityMentionModel.article_id)
                    .where(EntityMentionModel.entity_id == entity_id)
                )
            ).one()
            mention_rows = list(
                (
                    await session.execute(
                        select(
                            EntityMentionModel,
                            ArticleClaimModel.claim_text,
                            ArticleModel.title.label("article_title"),
                            ArticleModel.canonical_url,
                            ArticleModel.event_id,
                            ArticleModel.published_at,
                            EventModel.title.label("event_title"),
                            PublisherModel.name.label("publisher_name"),
                        )
                        .join(ArticleClaimModel, ArticleClaimModel.id == EntityMentionModel.claim_id)
                        .join(ArticleModel, ArticleModel.id == EntityMentionModel.article_id)
                        .join(EventModel, EventModel.id == ArticleModel.event_id)
                        .join(PublisherModel, PublisherModel.id == ArticleModel.publisher_id)
                        .where(EntityMentionModel.entity_id == entity_id)
                        .order_by(
                            func.coalesce(ArticleModel.published_at, ArticleModel.first_observed_at).desc(),
                            EntityMentionModel.created_at.desc(),
                        )
                        .limit(max(1, min(mention_limit, 200)))
                    )
                ).all()
            )
        return EntityProfileView(
            id=entity.id,
            entity_key=entity.entity_key,
            canonical_name=entity.canonical_name,
            normalized_name=entity.normalized_name,
            entity_type=entity.entity_type,
            country_code=entity.country_code,
            external_ids=dict(entity.external_ids or {}),
            metadata=dict(entity.metadata_ or {}),
            aliases=[
                EntityAliasSummaryView(
                    id=item.id,
                    alias=item.alias,
                    normalized_alias=item.normalized_alias,
                    language=item.language,
                    source=item.source,
                    confidence=float(item.confidence),
                )
                for item in aliases
            ],
            linked_external_ids=[
                EntityExternalIdSummaryView(
                    namespace=item.namespace,
                    external_id=item.external_id,
                    canonical_url=item.canonical_url,
                    provenance_url=item.provenance_url,
                    confidence=float(item.confidence),
                    verified_at=item.verified_at,
                )
                for item in external_ids
            ],
            claim_count=int(counts[0] or 0),
            article_count=int(counts[1] or 0),
            event_count=int(counts[2] or 0),
            publisher_count=int(counts[3] or 0),
            recent_mentions=[
                EntityMentionView(
                    id=row[0].id,
                    claim_id=row[0].claim_id,
                    claim_text=str(row.claim_text),
                    article_id=row[0].article_id,
                    article_title=str(row.article_title),
                    article_url=str(row.canonical_url),
                    event_id=row.event_id,
                    event_title=str(row.event_title),
                    publisher=str(row.publisher_name),
                    mention_text=row[0].mention_text,
                    link_basis=row[0].link_basis,
                    confidence=float(row[0].confidence),
                    published_at=row.published_at,
                    created_at=row[0].created_at,
                )
                for row in mention_rows
            ],
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            resolution_status=getattr(entity, "resolution_status", "active"),
            merged_into_entity_id=getattr(entity, "merged_into_entity_id", None),
        )

    async def refresh_mentions(self, entity_id: UUID) -> EntityMentionRefreshView | None:
        async with self._session_factory() as session, session.begin():
            entity = await session.get(CanonicalEntityModel, entity_id)
            if entity is None:
                return None
            if getattr(entity, "resolution_status", "active") != "active":
                raise ValueError("cannot refresh mentions for a merged entity; refresh the active target entity")
            aliases = list(
                (
                    await session.scalars(
                        select(EntityAliasModel).where(EntityAliasModel.entity_id == entity_id)
                    )
                ).all()
            )
            try:
                entity_type = EntityType(entity.entity_type)
            except ValueError:
                entity_type = EntityType.OTHER
            target_basis: dict[str, tuple[str, str]] = {
                normalize_entity_name(entity.canonical_name, entity_type=entity_type): (
                    entity.canonical_name,
                    "exact_canonical",
                )
            }
            for alias in aliases:
                target_basis.setdefault(
                    normalize_entity_name(alias.alias, entity_type=entity_type),
                    (alias.alias, "exact_alias"),
                )

            # Conservative candidate scan: only claims with an entities array in their extraction
            # features and only the latest article version. Identity is still decided by exact
            # normalized canonical/approved-alias equality below; fuzzy matches are never linked.
            current_version = aliased(ArticleVersionModel)
            newer_version = aliased(ArticleVersionModel)
            claim_statement = (
                select(ArticleClaimModel)
                .join(current_version, current_version.id == ArticleClaimModel.article_version_id)
                .where(ArticleClaimModel.extraction_features.has_key("entities"))  # type: ignore[attr-defined]
                .where(
                    ~select(newer_version.id)
                    .where(
                        newer_version.article_id == ArticleClaimModel.article_id,
                        newer_version.version_number > current_version.version_number,
                    )
                    .exists()
                )
                .order_by(ArticleClaimModel.created_at.desc())
                .execution_options(yield_per=500)
            )
            claims = await session.stream_scalars(claim_statement)
            await session.execute(delete(EntityMentionModel).where(EntityMentionModel.entity_id == entity_id))
            now = datetime.now(UTC)
            linked_claims: set[UUID] = set()
            linked_mentions = 0
            seen: set[tuple[UUID, str]] = set()
            async for claim in claims:
                raw_entities = claim.extraction_features.get("entities") if isinstance(claim.extraction_features, dict) else None
                if not isinstance(raw_entities, list):
                    continue
                for raw in raw_entities:
                    if not isinstance(raw, str) or not raw.strip():
                        continue
                    normalized = normalize_entity_name(raw, entity_type=entity_type)
                    basis = target_basis.get(normalized)
                    key = (claim.id, normalized)
                    if basis is None or key in seen:
                        continue
                    seen.add(key)
                    session.add(
                        EntityMentionModel(
                            entity_id=entity_id,
                            article_id=claim.article_id,
                            article_version_id=claim.article_version_id,
                            claim_id=claim.id,
                            mention_text=raw.strip(),
                            normalized_mention=normalized,
                            link_basis=basis[1],
                            confidence=1.0,
                            created_at=now,
                        )
                    )
                    linked_claims.add(claim.id)
                    linked_mentions += 1
            await session.flush()
            return EntityMentionRefreshView(
                entity_id=entity_id,
                linked_mentions=linked_mentions,
                linked_claims=len(linked_claims),
                scanned_aliases=len(target_basis),
            )
