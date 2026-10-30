from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.intelligence.dto import (
    CalibrationBenchmarkBatchCommand,
    CalibrationSnapshotView,
    EntityAliasCreateCommand,
    EntityAliasView,
    EntityResolutionView,
    EntityResolveCommand,
    OwnershipGroupCreateCommand,
    OwnershipGroupView,
    OwnershipMembershipCreateCommand,
    OwnershipMembershipView,
    OwnershipProvenanceCreateCommand,
    OwnershipProvenanceView,
    TemporalKnowledgeSearchHitView,
    TemporalKnowledgeSearchView,
)
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.calibration import (
    CalibrationObservation,
    assess_confidence_calibration,
)
from newsintel.domain.intelligence.entities import (
    CanonicalEntityRecord,
    EntityCandidate,
    EntityType,
    canonical_entity_key,
    normalize_entity_name,
    resolve_entity,
)
from newsintel.infrastructure.db.models import (
    CanonicalEntityModel,
    EntityAliasModel,
    MediaOwnershipGroupModel,
    PublisherModel,
    PublisherOwnershipMembershipModel,
    OwnershipProvenanceRecordModel,
    TemporalKnowledgeNodeModel,
    VerificationBenchmarkCaseModel,
    VerificationCalibrationSnapshotModel,
)


class OwnershipRegistryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_group(self, command: OwnershipGroupCreateCommand) -> OwnershipGroupView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            model = MediaOwnershipGroupModel(
                id=uuid7(),
                name=command.name,
                canonical_domain=command.canonical_domain,
                jurisdiction=command.jurisdiction,
                metadata_={
                    **command.metadata,
                    "guardrail": (
                        "Ownership registry data is used to estimate source independence, not "
                        "to infer editorial positions, factuality, or political bias."
                    ),
                },
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            await session.flush()
            return _group_view(model)

    async def list_groups(self) -> list[OwnershipGroupView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(MediaOwnershipGroupModel).order_by(MediaOwnershipGroupModel.name)
                    )
                ).all()
            )
            return [_group_view(item) for item in rows]

    async def add_membership(
        self,
        publisher_id: UUID,
        group_id: UUID,
        command: OwnershipMembershipCreateCommand,
    ) -> OwnershipMembershipView | None:
        now = datetime.now(UTC)
        if command.valid_from and command.valid_to and command.valid_to < command.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from")
        async with self._session_factory() as session, session.begin():
            publisher = await session.get(PublisherModel, publisher_id)
            group = await session.get(MediaOwnershipGroupModel, group_id)
            if publisher is None or group is None:
                return None
            model = PublisherOwnershipMembershipModel(
                id=uuid7(),
                publisher_id=publisher_id,
                group_id=group_id,
                relationship=command.relationship.value,
                ownership_fraction=command.ownership_fraction,
                valid_from=command.valid_from,
                valid_to=command.valid_to,
                provenance_url=str(command.provenance_url) if command.provenance_url else None,
                confidence=command.confidence,
                metadata_={
                    **command.metadata,
                    "provenance_required_for_high_stakes_use": True,
                },
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            await session.flush()
            return _membership_view(model, group.name)

    async def memberships_for_publisher(
        self,
        publisher_id: UUID,
    ) -> list[OwnershipMembershipView] | None:
        async with self._session_factory() as session:
            if await session.get(PublisherModel, publisher_id) is None:
                return None
            rows = list(
                (
                    await session.execute(
                        select(PublisherOwnershipMembershipModel, MediaOwnershipGroupModel)
                        .join(
                            MediaOwnershipGroupModel,
                            PublisherOwnershipMembershipModel.group_id == MediaOwnershipGroupModel.id,
                        )
                        .where(PublisherOwnershipMembershipModel.publisher_id == publisher_id)
                        .order_by(MediaOwnershipGroupModel.name)
                    )
                ).all()
            )
            return [_membership_view(item, group.name) for item, group in rows]


    async def add_provenance(
        self,
        membership_id: UUID,
        command: OwnershipProvenanceCreateCommand,
    ) -> OwnershipProvenanceView | None:
        now = datetime.now(UTC)
        if command.valid_from and command.valid_to and command.valid_to < command.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from")
        passage = command.passage_text.strip() if command.passage_text else None
        observed_at = _utc_datetime(command.observed_at) or now
        async with self._session_factory() as session, session.begin():
            membership = await session.get(PublisherOwnershipMembershipModel, membership_id)
            if membership is None:
                return None
            model = OwnershipProvenanceRecordModel(
                id=uuid7(),
                membership_id=membership_id,
                source_url=str(command.source_url),
                source_type=command.source_type,
                passage_text=passage,
                passage_sha256=sha256(passage.encode("utf-8")).hexdigest() if passage else None,
                observed_at=observed_at,
                valid_from=_utc_datetime(command.valid_from),
                valid_to=_utc_datetime(command.valid_to),
                confidence=command.confidence,
                metadata_={
                    **command.metadata,
                    "guardrail": (
                        "Ownership provenance records support independence analysis only. "
                        "They do not establish editorial stance or factual reliability."
                    ),
                },
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _ownership_provenance_view(model)

    async def provenance_for_membership(
        self,
        membership_id: UUID,
    ) -> list[OwnershipProvenanceView] | None:
        async with self._session_factory() as session:
            if await session.get(PublisherOwnershipMembershipModel, membership_id) is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(OwnershipProvenanceRecordModel)
                        .where(OwnershipProvenanceRecordModel.membership_id == membership_id)
                        .order_by(OwnershipProvenanceRecordModel.observed_at.desc())
                    )
                ).all()
            )
            return [_ownership_provenance_view(item) for item in rows]


class EntityResolutionService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(self, command: EntityResolveCommand) -> EntityResolutionView:
        async with self._session_factory() as session, session.begin():
            records = await _entity_records(session, command.entity_type, command.country_code)
            candidate = EntityCandidate(
                text=command.text,
                entity_type=command.entity_type,
                country_code=command.country_code,
                external_ids=tuple(sorted(command.external_ids.items())),
            )
            resolution = resolve_entity(candidate, tuple(records))
            if resolution.matched_entity_key:
                model = await session.scalar(
                    select(CanonicalEntityModel).where(
                        CanonicalEntityModel.entity_key == resolution.matched_entity_key
                    )
                )
                return EntityResolutionView(
                    entity_id=model.id if model else None,
                    entity_key=resolution.matched_entity_key,
                    canonical_name=model.canonical_name if model else None,
                    entity_type=model.entity_type if model else command.entity_type.value,
                    confidence=resolution.confidence,
                    match_basis=resolution.match_basis,
                    normalized_candidate=resolution.normalized_candidate,
                    ambiguous=resolution.ambiguous,
                    created=False,
                )
            if resolution.ambiguous or not command.create_if_unmatched:
                return EntityResolutionView(
                    entity_id=None,
                    entity_key=None,
                    canonical_name=None,
                    entity_type=command.entity_type.value,
                    confidence=resolution.confidence,
                    match_basis=resolution.match_basis,
                    normalized_candidate=resolution.normalized_candidate,
                    ambiguous=resolution.ambiguous,
                    created=False,
                )
            now = datetime.now(UTC)
            key = canonical_entity_key(
                command.text,
                entity_type=command.entity_type,
                country_code=command.country_code,
            )
            model = CanonicalEntityModel(
                id=uuid7(),
                entity_key=key,
                canonical_name=command.text,
                normalized_name=normalize_entity_name(command.text, entity_type=command.entity_type),
                entity_type=command.entity_type.value,
                country_code=command.country_code,
                external_ids=command.external_ids,
                metadata_={
                    "created_via": "explicit_resolution_request",
                    "guardrail": "Automatic creation does not merge ambiguous candidates.",
                },
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.add(
                EntityAliasModel(
                    id=uuid7(),
                    entity_id=model.id,
                    alias=command.text,
                    normalized_alias=model.normalized_name,
                    language=None,
                    source="canonical_name",
                    confidence=1.0,
                    created_at=now,
                )
            )
            await session.flush()
            return EntityResolutionView(
                entity_id=model.id,
                entity_key=model.entity_key,
                canonical_name=model.canonical_name,
                entity_type=model.entity_type,
                confidence=1.0,
                match_basis="created_unmatched",
                normalized_candidate=model.normalized_name,
                ambiguous=False,
                created=True,
            )

    async def add_alias(
        self,
        entity_id: UUID,
        command: EntityAliasCreateCommand,
    ) -> EntityAliasView | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            entity = await session.get(CanonicalEntityModel, entity_id)
            if entity is None:
                return None
            try:
                entity_type = EntityType(entity.entity_type)
            except ValueError:
                entity_type = EntityType.OTHER
            normalized = normalize_entity_name(command.alias, entity_type=entity_type)
            existing = await session.scalar(
                select(EntityAliasModel).where(
                    EntityAliasModel.entity_id == entity_id,
                    EntityAliasModel.normalized_alias == normalized,
                )
            )
            if existing is not None:
                return _alias_view(existing)
            model = EntityAliasModel(
                id=uuid7(),
                entity_id=entity_id,
                alias=command.alias,
                normalized_alias=normalized,
                language=command.language,
                source=command.source,
                confidence=command.confidence,
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _alias_view(model)


class VerificationCalibrationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add_cases(self, command: CalibrationBenchmarkBatchCommand) -> int:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            for item in command.cases:
                session.add(
                    VerificationBenchmarkCaseModel(
                        id=uuid7(),
                        claim_id=item.claim_id,
                        benchmark_set=item.benchmark_set,
                        case_key=item.case_key,
                        group_key=item.group_key,
                        source_document_key=item.source_document_key,
                        split=item.split,
                        topic_key=item.topic_key,
                        language=item.language,
                        jurisdiction=item.jurisdiction,
                        predicted_label=item.predicted_label.value,
                        predicted_confidence=item.predicted_confidence,
                        adjudicated_label=item.adjudicated_label.value,
                        adjudication_source=item.adjudication_source,
                        adjudicator_count=item.adjudicator_count,
                        adjudicated_at=item.adjudicated_at,
                        weight=item.weight,
                        metadata_=item.metadata,
                        created_at=now,
                    )
                )
            await session.flush()
        return len(command.cases)

    async def assess(
        self,
        benchmark_set: str,
        *,
        bin_count: int = 10,
    ) -> CalibrationSnapshotView:
        async with self._session_factory() as session, session.begin():
            rows = list(
                (
                    await session.scalars(
                        select(VerificationBenchmarkCaseModel)
                        .where(VerificationBenchmarkCaseModel.benchmark_set == benchmark_set)
                        .order_by(VerificationBenchmarkCaseModel.created_at)
                    )
                ).all()
            )
            decided_rows = [
                item for item in rows
                if item.predicted_label.casefold() != "not_checkable"
            ]
            observations = tuple(
                CalibrationObservation(
                    predicted_confidence=item.predicted_confidence,
                    outcome_correct=item.predicted_label.casefold() == item.adjudicated_label.casefold(),
                    weight=item.weight,
                )
                for item in decided_rows
            )
            assessment = assess_confidence_calibration(observations, bin_count=bin_count)
            now = datetime.now(UTC)
            bins = [
                {
                    "lower": item.lower,
                    "upper": item.upper,
                    "count": item.count,
                    "weight": item.weight,
                    "mean_confidence": item.mean_confidence,
                    "empirical_accuracy": item.empirical_accuracy,
                    "calibration_gap": item.calibration_gap,
                }
                for item in assessment.bins
            ]
            model = VerificationCalibrationSnapshotModel(
                id=uuid7(),
                benchmark_set=benchmark_set,
                methodology_version=assessment.methodology_version,
                observation_count=assessment.observation_count,
                effective_weight=assessment.effective_weight,
                brier_score=assessment.brier_score,
                expected_calibration_error=assessment.expected_calibration_error,
                mean_confidence=assessment.mean_confidence,
                empirical_accuracy=assessment.empirical_accuracy,
                bins=bins,
                metadata_={
                    "interpretation": assessment.interpretation,
                    "case_count": len(rows),
                    "decided_case_count": len(decided_rows),
                    "abstention_case_count": len(rows) - len(decided_rows),
                    "guardrail": (
                        "Calibration requires externally adjudicated labels and is computed only "
                        "for substantive verdicts. Not-checkable abstentions are measured through "
                        "decision coverage instead of being treated as zero-confidence verdicts."
                    ),
                },
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _calibration_view(model)

    async def history(
        self,
        benchmark_set: str,
        *,
        limit: int = 50,
    ) -> list[CalibrationSnapshotView]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(VerificationCalibrationSnapshotModel)
                        .where(VerificationCalibrationSnapshotModel.benchmark_set == benchmark_set)
                        .order_by(VerificationCalibrationSnapshotModel.created_at.desc())
                        .limit(limit)
                    )
                ).all()
            )
            return [_calibration_view(item) for item in rows]


class TemporalKnowledgeSearchService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(
        self,
        query: str,
        *,
        node_types: list[str] | None = None,
        as_of: datetime | None = None,
        limit: int = 25,
    ) -> TemporalKnowledgeSearchView:
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        ts_vector = func.to_tsvector("simple", TemporalKnowledgeNodeModel.search_text)
        ts_query = func.plainto_tsquery("simple", query)
        score = func.ts_rank_cd(ts_vector, ts_query)
        statement = select(TemporalKnowledgeNodeModel, score.label("rank")).where(
            ts_vector.op("@@")(ts_query)
        )
        if node_types:
            statement = statement.where(TemporalKnowledgeNodeModel.node_type.in_(node_types))
        if as_of is not None:
            statement = statement.where(
                TemporalKnowledgeNodeModel.observed_at <= as_of,
                (TemporalKnowledgeNodeModel.valid_from.is_(None))
                | (TemporalKnowledgeNodeModel.valid_from <= as_of),
                (TemporalKnowledgeNodeModel.valid_to.is_(None))
                | (TemporalKnowledgeNodeModel.valid_to >= as_of),
            )
        statement = statement.order_by(score.desc(), TemporalKnowledgeNodeModel.observed_at.desc()).limit(limit)
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).all())
        return TemporalKnowledgeSearchView(
            query=query,
            as_of=as_of,
            node_types=node_types or [],
            hits=[
                TemporalKnowledgeSearchHitView(
                    event_id=node.event_id,
                    node_key=node.node_key,
                    node_type=node.node_type,
                    label=node.label,
                    score=round(float(rank or 0.0), 6),
                    observed_at=node.observed_at,
                    valid_from=node.valid_from,
                    valid_to=node.valid_to,
                    payload=node.payload,
                )
                for node, rank in rows
            ],
            generated_at=datetime.now(UTC),
            interpretation=(
                "Search uses indexed temporal knowledge already stored by the platform. An as-of "
                "filter prevents later observations from leaking into earlier historical queries."
            ),
        )


async def _entity_records(
    session: AsyncSession,
    entity_type: EntityType,
    country_code: str | None,
) -> list[CanonicalEntityRecord]:
    statement = select(CanonicalEntityModel)
    if entity_type is not EntityType.OTHER:
        statement = statement.where(CanonicalEntityModel.entity_type == entity_type.value)
    if country_code:
        statement = statement.where(
            (CanonicalEntityModel.country_code == country_code)
            | CanonicalEntityModel.country_code.is_(None)
        )
    models = list((await session.scalars(statement.limit(1000))).all())
    if not models:
        return []
    aliases = list(
        (
            await session.scalars(
                select(EntityAliasModel).where(
                    EntityAliasModel.entity_id.in_([item.id for item in models])
                )
            )
        ).all()
    )
    aliases_by_id: dict[UUID, list[str]] = {}
    for alias in aliases:
        aliases_by_id.setdefault(alias.entity_id, []).append(alias.alias)
    return [
        CanonicalEntityRecord(
            entity_key=item.entity_key,
            canonical_name=item.canonical_name,
            entity_type=EntityType(item.entity_type),
            aliases=tuple(aliases_by_id.get(item.id, [])),
            country_code=item.country_code,
            external_ids=tuple(sorted(item.external_ids.items())),
        )
        for item in models
    ]


def _ownership_provenance_view(item: OwnershipProvenanceRecordModel) -> OwnershipProvenanceView:
    return OwnershipProvenanceView(
        id=item.id,
        membership_id=item.membership_id,
        source_url=item.source_url,
        source_type=item.source_type,
        passage_text=item.passage_text,
        passage_sha256=item.passage_sha256,
        observed_at=item.observed_at,
        valid_from=item.valid_from,
        valid_to=item.valid_to,
        confidence=item.confidence,
        metadata=item.metadata_,
        created_at=item.created_at,
    )


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _group_view(item: MediaOwnershipGroupModel) -> OwnershipGroupView:
    return OwnershipGroupView(
        id=item.id,
        name=item.name,
        canonical_domain=item.canonical_domain,
        jurisdiction=item.jurisdiction,
        metadata=item.metadata_,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _membership_view(
    item: PublisherOwnershipMembershipModel,
    group_name: str,
) -> OwnershipMembershipView:
    return OwnershipMembershipView(
        id=item.id,
        publisher_id=item.publisher_id,
        group_id=item.group_id,
        group_name=group_name,
        relationship=item.relationship,
        ownership_fraction=item.ownership_fraction,
        valid_from=item.valid_from,
        valid_to=item.valid_to,
        provenance_url=item.provenance_url,
        confidence=item.confidence,
        metadata=item.metadata_,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _alias_view(item: EntityAliasModel) -> EntityAliasView:
    return EntityAliasView(
        id=item.id,
        entity_id=item.entity_id,
        alias=item.alias,
        normalized_alias=item.normalized_alias,
        language=item.language,
        source=item.source,
        confidence=item.confidence,
        created_at=item.created_at,
    )


def _calibration_view(item: VerificationCalibrationSnapshotModel) -> CalibrationSnapshotView:
    return CalibrationSnapshotView(
        id=item.id,
        benchmark_set=item.benchmark_set,
        methodology_version=item.methodology_version,
        observation_count=item.observation_count,
        effective_weight=item.effective_weight,
        brier_score=item.brier_score,
        expected_calibration_error=item.expected_calibration_error,
        mean_confidence=item.mean_confidence,
        empirical_accuracy=item.empirical_accuracy,
        bins=item.bins,
        interpretation=str(item.metadata_.get("interpretation") or ""),
        metadata=item.metadata_,
        created_at=item.created_at,
    )
