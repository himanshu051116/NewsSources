from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

TEMPORAL_GRAPH_VERSION = "temporal-event-knowledge-graph-v1"


@dataclass(frozen=True, slots=True)
class KnowledgeClaimInput:
    claim_id: str
    claim_text: str
    observed_at: datetime
    claim_type: str | None
    entities: tuple[str, ...]
    attribution_speaker: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeCommitmentInput:
    commitment_id: str
    text: str
    commitment_type: str
    observed_at: datetime
    actor: str | None = None
    deadline_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeVerificationInput:
    verification_id: str
    claim_id: str
    label: str
    confidence: float | None
    methodology_version: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeEvidenceInput:
    evidence_id: str
    claim_id: str
    source_url: str
    stance: str
    evidence_class: str | None
    temporal_relation: str
    primary_source: bool
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeNode:
    node_key: str
    node_type: str
    label: str
    observed_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class KnowledgeEdge:
    edge_key: str
    source_key: str
    target_key: str
    relation: str
    observed_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class TemporalKnowledgeGraph:
    graph_version: str
    event_key: str
    nodes: tuple[KnowledgeNode, ...]
    edges: tuple[KnowledgeEdge, ...]


def build_event_knowledge_graph(
    *,
    event_id: str,
    event_title: str,
    event_observed_at: datetime,
    claims: tuple[KnowledgeClaimInput, ...],
    commitments: tuple[KnowledgeCommitmentInput, ...] = (),
    verifications: tuple[KnowledgeVerificationInput, ...] = (),
    evidence: tuple[KnowledgeEvidenceInput, ...] = (),
    entity_key_overrides: dict[str, str] | None = None,
) -> TemporalKnowledgeGraph:
    event_key = f"event:{event_id}"
    entity_key_overrides = entity_key_overrides or {}
    node_by_key: dict[str, KnowledgeNode] = {
        event_key: KnowledgeNode(
            node_key=event_key,
            node_type="event",
            label=event_title,
            observed_at=event_observed_at,
            valid_from=event_observed_at,
            valid_to=None,
            payload={"event_id": event_id},
        )
    }
    edges: dict[str, KnowledgeEdge] = {}

    for claim in claims:
        claim_key = f"claim:{claim.claim_id}"
        node_by_key[claim_key] = KnowledgeNode(
            node_key=claim_key,
            node_type="claim",
            label=claim.claim_text,
            observed_at=claim.observed_at,
            valid_from=claim.valid_from,
            valid_to=claim.valid_to,
            payload={"claim_id": claim.claim_id, "claim_type": claim.claim_type},
        )
        _add_edge(
            edges,
            source_key=event_key,
            target_key=claim_key,
            relation="has_claim",
            observed_at=claim.observed_at,
            valid_from=claim.valid_from,
            valid_to=claim.valid_to,
            payload={},
        )
        for entity in claim.entities:
            normalized = " ".join(entity.split()).strip()
            if not normalized:
                continue
            canonical_key = entity_key_overrides.get(normalized)
            entity_key = f"entity:{canonical_key}" if canonical_key else _semantic_key("entity", normalized)
            node_by_key.setdefault(
                entity_key,
                KnowledgeNode(
                    node_key=entity_key,
                    node_type="entity",
                    label=normalized,
                    observed_at=claim.observed_at,
                    valid_from=None,
                    valid_to=None,
                    payload={"canonical_entity_key": canonical_key},
                ),
            )
            _add_edge(
                edges,
                source_key=claim_key,
                target_key=entity_key,
                relation="mentions",
                observed_at=claim.observed_at,
                valid_from=claim.valid_from,
                valid_to=claim.valid_to,
                payload={},
            )
        if claim.attribution_speaker:
            speaker = " ".join(claim.attribution_speaker.split()).strip()
            if speaker:
                speaker_key = _semantic_key("actor", speaker)
                node_by_key.setdefault(
                    speaker_key,
                    KnowledgeNode(
                        node_key=speaker_key,
                        node_type="actor",
                        label=speaker,
                        observed_at=claim.observed_at,
                        valid_from=None,
                        valid_to=None,
                        payload={},
                    ),
                )
                _add_edge(
                    edges,
                    source_key=claim_key,
                    target_key=speaker_key,
                    relation="attributed_to",
                    observed_at=claim.observed_at,
                    valid_from=claim.valid_from,
                    valid_to=claim.valid_to,
                    payload={},
                )

    for verification in verifications:
        claim_key = f"claim:{verification.claim_id}"
        if claim_key not in node_by_key:
            continue
        verification_key = f"verification:{verification.verification_id}"
        node_by_key[verification_key] = KnowledgeNode(
            node_key=verification_key,
            node_type="verification",
            label=verification.label,
            observed_at=verification.observed_at,
            valid_from=verification.observed_at,
            valid_to=None,
            payload={
                "verification_id": verification.verification_id,
                "label": verification.label,
                "confidence": verification.confidence,
                "methodology_version": verification.methodology_version,
            },
        )
        _add_edge(
            edges,
            source_key=claim_key,
            target_key=verification_key,
            relation="verification_revision",
            observed_at=verification.observed_at,
            valid_from=verification.observed_at,
            valid_to=None,
            payload={},
        )

    for item in evidence:
        claim_key = f"claim:{item.claim_id}"
        if claim_key not in node_by_key:
            continue
        evidence_key = f"evidence:{item.evidence_id}"
        node_by_key[evidence_key] = KnowledgeNode(
            node_key=evidence_key,
            node_type="evidence",
            label=item.source_url,
            observed_at=item.observed_at,
            valid_from=item.observed_at,
            valid_to=None,
            payload={
                "evidence_id": item.evidence_id,
                "source_url": item.source_url,
                "stance": item.stance,
                "evidence_class": item.evidence_class,
                "temporal_relation": item.temporal_relation,
                "primary_source": item.primary_source,
            },
        )
        _add_edge(
            edges,
            source_key=claim_key,
            target_key=evidence_key,
            relation="has_evidence",
            observed_at=item.observed_at,
            valid_from=item.observed_at,
            valid_to=None,
            payload={"stance": item.stance},
        )

    for commitment in commitments:
        commitment_key = f"commitment:{commitment.commitment_id}"
        node_by_key[commitment_key] = KnowledgeNode(
            node_key=commitment_key,
            node_type="commitment",
            label=commitment.text,
            observed_at=commitment.observed_at,
            valid_from=commitment.observed_at,
            valid_to=commitment.deadline_at,
            payload={
                "commitment_id": commitment.commitment_id,
                "commitment_type": commitment.commitment_type,
                "deadline_at": commitment.deadline_at.isoformat() if commitment.deadline_at else None,
            },
        )
        _add_edge(
            edges,
            source_key=event_key,
            target_key=commitment_key,
            relation="tracks_commitment",
            observed_at=commitment.observed_at,
            valid_from=commitment.observed_at,
            valid_to=commitment.deadline_at,
            payload={},
        )
        if commitment.actor:
            actor = " ".join(commitment.actor.split()).strip()
            if actor:
                actor_key = _semantic_key("actor", actor)
                node_by_key.setdefault(
                    actor_key,
                    KnowledgeNode(
                        node_key=actor_key,
                        node_type="actor",
                        label=actor,
                        observed_at=commitment.observed_at,
                        valid_from=None,
                        valid_to=None,
                        payload={},
                    ),
                )
                _add_edge(
                    edges,
                    source_key=commitment_key,
                    target_key=actor_key,
                    relation="committed_by",
                    observed_at=commitment.observed_at,
                    valid_from=commitment.observed_at,
                    valid_to=commitment.deadline_at,
                    payload={},
                )

    return TemporalKnowledgeGraph(
        graph_version=TEMPORAL_GRAPH_VERSION,
        event_key=event_key,
        nodes=tuple(sorted(node_by_key.values(), key=lambda item: item.node_key)),
        edges=tuple(sorted(edges.values(), key=lambda item: item.edge_key)),
    )


def graph_as_of(graph: TemporalKnowledgeGraph, as_of: datetime) -> TemporalKnowledgeGraph:
    nodes = tuple(
        node
        for node in graph.nodes
        if node.observed_at <= as_of
        and (node.valid_from is None or node.valid_from <= as_of)
        and (node.valid_to is None or as_of <= node.valid_to)
    )
    visible = {node.node_key for node in nodes}
    edges = tuple(
        edge
        for edge in graph.edges
        if edge.source_key in visible
        and edge.target_key in visible
        and edge.observed_at <= as_of
        and (edge.valid_from is None or edge.valid_from <= as_of)
        and (edge.valid_to is None or as_of <= edge.valid_to)
    )
    return TemporalKnowledgeGraph(
        graph_version=graph.graph_version,
        event_key=graph.event_key,
        nodes=nodes,
        edges=edges,
    )


def _semantic_key(kind: str, label: str) -> str:
    digest = sha256(label.casefold().encode("utf-8")).hexdigest()[:24]
    return f"{kind}:{digest}"


def _add_edge(
    edges: dict[str, KnowledgeEdge],
    *,
    source_key: str,
    target_key: str,
    relation: str,
    observed_at: datetime,
    valid_from: datetime | None,
    valid_to: datetime | None,
    payload: dict[str, object],
) -> None:
    material = f"{source_key}|{relation}|{target_key}"
    edge_key = sha256(material.encode("utf-8")).hexdigest()
    existing = edges.get(edge_key)
    if existing is not None and existing.observed_at <= observed_at:
        return
    edges[edge_key] = KnowledgeEdge(
        edge_key=edge_key,
        source_key=source_key,
        target_key=target_key,
        relation=relation,
        observed_at=observed_at,
        valid_from=valid_from,
        valid_to=valid_to,
        payload=payload,
    )
