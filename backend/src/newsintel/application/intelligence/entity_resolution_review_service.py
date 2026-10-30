from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.intelligence.entity_intelligence_dto import (
    EntityConflictScanView,
    EntityMergeCommand,
    EntityResolutionActionView,
    EntityResolutionCandidateView,
    EntitySplitAliasCommand,
)
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.entities import (
    EntityType,
    canonical_entity_key,
    normalize_entity_name,
)
from newsintel.infrastructure.db.models import (
    CanonicalEntityModel,
    EntityAliasModel,
    EntityExternalIdentifierModel,
    EntityMentionModel,
    EntityResolutionActionModel,
    EntityResolutionCandidateModel,
)


class EntityResolutionReviewService:
    """Human-directed identity maintenance.

    Automatic work is intentionally limited to deterministic conflict discovery. Merge/split
    actions always require an authenticated verifier and a written rationale.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def scan_conflicts(self, *, limit: int = 500) -> EntityConflictScanView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            entities = list(
                (
                    await session.scalars(
                        select(CanonicalEntityModel)
                        .where(CanonicalEntityModel.resolution_status == "active")
                        .order_by(CanonicalEntityModel.created_at.asc())
                    )
                ).all()
            )
            ids = [item.id for item in entities]
            aliases = list(
                (
                    await session.scalars(
                        select(EntityAliasModel).where(EntityAliasModel.entity_id.in_(ids))
                    )
                ).all()
            ) if ids else []
            labels: dict[str, dict[UUID, list[dict[str, str]]]] = {}
            by_id = {item.id: item for item in entities}
            for entity in entities:
                if entity.normalized_name:
                    labels.setdefault(entity.normalized_name, {}).setdefault(entity.id, []).append(
                        {"basis": "canonical_name", "text": entity.canonical_name}
                    )
            for alias in aliases:
                if alias.normalized_alias:
                    labels.setdefault(alias.normalized_alias, {}).setdefault(alias.entity_id, []).append(
                        {"basis": "approved_alias", "text": alias.alias}
                    )

            detected = 0
            created = 0
            for normalized, entity_map in sorted(labels.items()):
                entity_ids = sorted(entity_map, key=str)
                if len(entity_ids) < 2:
                    continue
                detected += 1
                if detected > max(1, min(limit, 5_000)):
                    break
                key = _candidate_key("shared_normalized_identity", normalized, entity_ids)
                existing = await session.scalar(
                    select(EntityResolutionCandidateModel).where(
                        EntityResolutionCandidateModel.candidate_key == key
                    )
                )
                if existing is not None:
                    continue
                evidence = {
                    "entities": [
                        {
                            "id": str(entity_id),
                            "canonical_name": by_id[entity_id].canonical_name,
                            "entity_type": by_id[entity_id].entity_type,
                            "country_code": by_id[entity_id].country_code,
                            "matches": entity_map[entity_id],
                        }
                        for entity_id in entity_ids
                    ],
                    "guardrail": "Shared normalized identity is a review signal, not proof that the entities are identical.",
                }
                session.add(
                    EntityResolutionCandidateModel(
                        id=uuid7(),
                        candidate_key=key,
                        candidate_type="shared_normalized_identity",
                        normalized_value=normalized,
                        entity_ids=[str(item) for item in entity_ids],
                        evidence=evidence,
                        status="pending",
                        resolved_action_id=None,
                        created_at=now,
                        resolved_at=None,
                    )
                )
                created += 1
            await session.flush()
            pending_count = int(
                (await session.scalar(
                    select(func.count(EntityResolutionCandidateModel.id)).where(
                        EntityResolutionCandidateModel.status == "pending"
                    )
                ))
                or 0
            )
            return EntityConflictScanView(
                detected_candidates=min(detected, max(1, min(limit, 5_000))),
                new_candidates=created,
                pending_candidates=pending_count,
            )

    async def list_candidates(
        self,
        *,
        status: str = "pending",
        limit: int = 100,
    ) -> list[EntityResolutionCandidateView]:
        normalized_status = status.strip().lower()
        if normalized_status not in {"pending", "accepted", "rejected", "all"}:
            raise ValueError("status must be pending, accepted, rejected, or all")
        async with self._session_factory() as session:
            statement = select(EntityResolutionCandidateModel)
            if normalized_status != "all":
                statement = statement.where(EntityResolutionCandidateModel.status == normalized_status)
            rows = list(
                (
                    await session.scalars(
                        statement.order_by(EntityResolutionCandidateModel.created_at.desc()).limit(max(1, min(limit, 500)))
                    )
                ).all()
            )
        return [_candidate_view(item) for item in rows]

    async def reject_candidate(
        self,
        candidate_id: UUID,
        *,
        actor_user_id: UUID | None,
        rationale: str,
    ) -> EntityResolutionActionView | None:
        note = rationale.strip()
        if len(note) < 4:
            raise ValueError("a rejection rationale is required")
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            candidate = await session.get(EntityResolutionCandidateModel, candidate_id)
            if candidate is None:
                return None
            if candidate.status != "pending":
                raise ValueError("candidate has already been resolved")
            entity_ids = [UUID(str(item)) for item in candidate.entity_ids]
            if not entity_ids:
                raise ValueError("candidate has no source entity")
            action = EntityResolutionActionModel(
                id=uuid7(),
                action_type="reject_candidate",
                source_entity_id=entity_ids[0],
                target_entity_id=None,
                new_entity_id=None,
                alias_id=None,
                candidate_id=candidate.id,
                rationale=note,
                actor_user_id=actor_user_id,
                metadata_={"candidate_type": candidate.candidate_type, "normalized_value": candidate.normalized_value},
                created_at=now,
            )
            session.add(action)
            await session.flush()
            candidate.status = "rejected"
            candidate.resolved_action_id = action.id
            candidate.resolved_at = now
            return _action_view(action)

    async def merge(
        self,
        command: EntityMergeCommand,
        *,
        actor_user_id: UUID | None,
    ) -> EntityResolutionActionView:
        if command.source_entity_id == command.target_entity_id:
            raise ValueError("source and target entity must be different")
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            source = await session.get(CanonicalEntityModel, command.source_entity_id)
            target = await session.get(CanonicalEntityModel, command.target_entity_id)
            if source is None or target is None:
                raise ValueError("source or target entity not found")
            _assert_active_entity(source, "source")
            _assert_active_entity(target, "target")
            if source.entity_type != target.entity_type:
                raise ValueError("cross-type entity merges are not allowed")
            if source.country_code and target.country_code and source.country_code != target.country_code:
                raise ValueError("entities with conflicting country codes cannot be merged")
            candidate = await self._candidate_for_update(session, command.candidate_id)
            if candidate is not None:
                candidate_ids = {UUID(str(item)) for item in candidate.entity_ids}
                if not {source.id, target.id}.issubset(candidate_ids):
                    raise ValueError("merge entities are not both part of the selected candidate")

            target_aliases = {
                item.normalized_alias: item
                for item in (
                    await session.scalars(select(EntityAliasModel).where(EntityAliasModel.entity_id == target.id))
                ).all()
            }
            moved_aliases = 0
            collapsed_aliases = 0
            source_aliases = list(
                (
                    await session.scalars(select(EntityAliasModel).where(EntityAliasModel.entity_id == source.id))
                ).all()
            )
            for alias in source_aliases:
                if alias.normalized_alias in target_aliases:
                    await session.delete(alias)
                    collapsed_aliases += 1
                else:
                    alias.entity_id = target.id
                    target_aliases[alias.normalized_alias] = alias
                    moved_aliases += 1
            source_name_normalized = normalize_entity_name(
                source.canonical_name,
                entity_type=_entity_type(source.entity_type),
            )
            if source_name_normalized and source_name_normalized not in target_aliases:
                alias = EntityAliasModel(
                    id=uuid7(),
                    entity_id=target.id,
                    alias=source.canonical_name,
                    normalized_alias=source_name_normalized,
                    language=None,
                    source="entity_merge",
                    confidence=1.0,
                    created_at=now,
                )
                session.add(alias)
                target_aliases[source_name_normalized] = alias
                moved_aliases += 1

            external_rows = list(
                (
                    await session.scalars(
                        select(EntityExternalIdentifierModel).where(EntityExternalIdentifierModel.entity_id == source.id)
                    )
                ).all()
            )
            for item in external_rows:
                item.entity_id = target.id

            target_mention_keys = {
                (item.claim_id, item.normalized_mention)
                for item in (
                    await session.scalars(select(EntityMentionModel).where(EntityMentionModel.entity_id == target.id))
                ).all()
            }
            source_mentions = list(
                (
                    await session.scalars(select(EntityMentionModel).where(EntityMentionModel.entity_id == source.id))
                ).all()
            )
            moved_mentions = 0
            collapsed_mentions = 0
            for mention in source_mentions:
                key = (mention.claim_id, mention.normalized_mention)
                if key in target_mention_keys:
                    await session.delete(mention)
                    collapsed_mentions += 1
                else:
                    mention.entity_id = target.id
                    target_mention_keys.add(key)
                    moved_mentions += 1

            merged_external_ids = dict(target.external_ids or {})
            for key, value in dict(source.external_ids or {}).items():
                merged_external_ids.setdefault(key, value)
            target.external_ids = merged_external_ids
            target.updated_at = now
            source.resolution_status = "merged"
            source.merged_into_entity_id = target.id
            source.updated_at = now
            source.metadata_ = {
                **dict(source.metadata_ or {}),
                "merged_into_entity_id": str(target.id),
                "merged_at": now.isoformat(),
                "merge_guardrail": "Source canonical record preserved for audit; active retrieval resolves to the selected target.",
            }

            action = EntityResolutionActionModel(
                id=uuid7(),
                action_type="merge",
                source_entity_id=source.id,
                target_entity_id=target.id,
                new_entity_id=None,
                alias_id=None,
                candidate_id=candidate.id if candidate else None,
                rationale=command.rationale.strip(),
                actor_user_id=actor_user_id,
                metadata_={
                    "moved_aliases": moved_aliases,
                    "collapsed_aliases": collapsed_aliases,
                    "moved_mentions": moved_mentions,
                    "collapsed_mentions": collapsed_mentions,
                    "moved_external_identifiers": len(external_rows),
                },
                created_at=now,
            )
            session.add(action)
            await session.flush()
            if candidate is not None:
                candidate.status = "accepted"
                candidate.resolved_action_id = action.id
                candidate.resolved_at = now
            return _action_view(action)

    async def split_alias(
        self,
        source_entity_id: UUID,
        command: EntitySplitAliasCommand,
        *,
        actor_user_id: UUID | None,
    ) -> EntityResolutionActionView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            source = await session.get(CanonicalEntityModel, source_entity_id)
            alias = await session.get(EntityAliasModel, command.alias_id)
            if source is None or alias is None or alias.entity_id != source_entity_id:
                raise ValueError("source entity or alias not found")
            _assert_active_entity(source, "source")
            if alias.normalized_alias == source.normalized_name:
                raise ValueError("the canonical-name alias cannot be split; choose a non-canonical alias")
            candidate = await self._candidate_for_update(session, command.candidate_id)
            if candidate is not None and source.id not in {UUID(str(item)) for item in candidate.entity_ids}:
                raise ValueError("source entity is not part of the selected candidate")
            entity_type = _entity_type(command.entity_type or source.entity_type)
            country_code = (command.country_code or source.country_code or "").strip().upper() or None
            canonical_name = (command.canonical_name or alias.alias).strip()
            if not canonical_name:
                raise ValueError("canonical name is required")
            normalized_name = normalize_entity_name(canonical_name, entity_type=entity_type)
            key = canonical_entity_key(canonical_name, entity_type=entity_type, country_code=country_code)
            duplicate = await session.scalar(
                select(CanonicalEntityModel).where(
                    CanonicalEntityModel.entity_key == key,
                    CanonicalEntityModel.resolution_status == "active",
                )
            )
            if duplicate is not None:
                raise ValueError("an active canonical entity already exists for the requested split identity")
            new_entity = CanonicalEntityModel(
                id=uuid7(),
                entity_key=key,
                canonical_name=canonical_name,
                normalized_name=normalized_name,
                entity_type=entity_type.value,
                country_code=country_code,
                external_ids={},
                metadata_={
                    "created_via": "human_alias_split",
                    "split_from_entity_id": str(source.id),
                    "guardrail": "Only exact mention links for the selected alias were moved automatically.",
                },
                created_at=now,
                updated_at=now,
                resolution_status="active",
                merged_into_entity_id=None,
            )
            session.add(new_entity)
            canonical_alias = EntityAliasModel(
                id=uuid7(),
                entity_id=new_entity.id,
                alias=canonical_name,
                normalized_alias=normalized_name,
                language=alias.language,
                source="split_canonical_name",
                confidence=1.0,
                created_at=now,
            )
            session.add(canonical_alias)
            if alias.normalized_alias != normalized_name:
                alias.entity_id = new_entity.id
            else:
                await session.delete(alias)

            mentions = list(
                (
                    await session.scalars(
                        select(EntityMentionModel).where(
                            EntityMentionModel.entity_id == source.id,
                            EntityMentionModel.normalized_mention == alias.normalized_alias,
                        )
                    )
                ).all()
            )
            for mention in mentions:
                mention.entity_id = new_entity.id
                mention.link_basis = "human_alias_split"
                mention.confidence = 1.0
            source.updated_at = now
            action = EntityResolutionActionModel(
                id=uuid7(),
                action_type="split_alias",
                source_entity_id=source.id,
                target_entity_id=None,
                new_entity_id=new_entity.id,
                alias_id=command.alias_id,
                candidate_id=candidate.id if candidate else None,
                rationale=command.rationale.strip(),
                actor_user_id=actor_user_id,
                metadata_={
                    "split_alias": alias.alias,
                    "normalized_alias": alias.normalized_alias,
                    "moved_mentions": len(mentions),
                },
                created_at=now,
            )
            session.add(action)
            await session.flush()
            if candidate is not None:
                candidate.status = "accepted"
                candidate.resolved_action_id = action.id
                candidate.resolved_at = now
            return _action_view(action)

    async def history(self, *, limit: int = 100) -> list[EntityResolutionActionView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(EntityResolutionActionModel)
                        .order_by(EntityResolutionActionModel.created_at.desc())
                        .limit(max(1, min(limit, 500)))
                    )
                ).all()
            )
        return [_action_view(item) for item in rows]

    async def _candidate_for_update(
        self,
        session: AsyncSession,
        candidate_id: UUID | None,
    ) -> EntityResolutionCandidateModel | None:
        if candidate_id is None:
            return None
        candidate = await session.get(EntityResolutionCandidateModel, candidate_id, with_for_update=True)
        if candidate is None:
            raise ValueError("resolution candidate not found")
        if candidate.status != "pending":
            raise ValueError("resolution candidate has already been resolved")
        return candidate


def _assert_active_entity(entity: CanonicalEntityModel, label: str) -> None:
    if getattr(entity, "resolution_status", "active") != "active":
        raise ValueError(f"{label} entity is not active")


def _entity_type(value: str) -> EntityType:
    try:
        return EntityType(value)
    except ValueError as exc:
        raise ValueError(f"unsupported entity type: {value}") from exc


def _candidate_key(candidate_type: str, normalized_value: str, entity_ids: list[UUID]) -> str:
    material = f"{candidate_type}|{normalized_value}|{'|'.join(str(item) for item in sorted(entity_ids, key=str))}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]


def _candidate_view(item: EntityResolutionCandidateModel) -> EntityResolutionCandidateView:
    return EntityResolutionCandidateView(
        id=item.id,
        candidate_key=item.candidate_key,
        candidate_type=item.candidate_type,
        normalized_value=item.normalized_value,
        entity_ids=[UUID(str(value)) for value in item.entity_ids],
        evidence=dict(item.evidence or {}),
        status=item.status,
        resolved_action_id=item.resolved_action_id,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


def _action_view(item: EntityResolutionActionModel) -> EntityResolutionActionView:
    return EntityResolutionActionView(
        id=item.id,
        action_type=item.action_type,
        source_entity_id=item.source_entity_id,
        target_entity_id=item.target_entity_id,
        new_entity_id=item.new_entity_id,
        alias_id=item.alias_id,
        candidate_id=item.candidate_id,
        rationale=item.rationale,
        actor_user_id=item.actor_user_id,
        metadata=dict(item.metadata_ or {}),
        created_at=item.created_at,
    )
