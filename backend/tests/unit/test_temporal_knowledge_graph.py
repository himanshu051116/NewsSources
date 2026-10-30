from datetime import UTC, datetime, timedelta

from newsintel.domain.intelligence.knowledge_graph import (
    KnowledgeClaimInput,
    KnowledgeCommitmentInput,
    KnowledgeEvidenceInput,
    KnowledgeVerificationInput,
    build_event_knowledge_graph,
    graph_as_of,
)


def test_graph_connects_claims_entities_attribution_and_commitments() -> None:
    t0 = datetime(2026, 8, 10, tzinfo=UTC)
    graph = build_event_knowledge_graph(
        event_id="event-1",
        event_title="Project approval",
        event_observed_at=t0,
        claims=(
            KnowledgeClaimInput(
                claim_id="claim-1",
                claim_text="The Ministry approved Project Aurora in 2026.",
                observed_at=t0 + timedelta(hours=1),
                claim_type="event_occurrence",
                entities=("Ministry", "Project Aurora"),
                attribution_speaker="Ministry",
            ),
        ),
        commitments=(
            KnowledgeCommitmentInput(
                commitment_id="commit-1",
                text="Project Aurora will open by 2028.",
                commitment_type="deadline",
                observed_at=t0 + timedelta(hours=2),
                actor="Ministry",
                deadline_at=datetime(2028, 12, 31, tzinfo=UTC),
            ),
        ),
        verifications=(
            KnowledgeVerificationInput(
                verification_id="verification-1",
                claim_id="claim-1",
                label="supported",
                confidence=0.9,
                methodology_version="v1",
                observed_at=t0 + timedelta(hours=3),
            ),
        ),
        evidence=(
            KnowledgeEvidenceInput(
                evidence_id="evidence-1",
                claim_id="claim-1",
                source_url="https://records.example/order/1",
                stance="support",
                evidence_class="government_record",
                temporal_relation="same_window",
                primary_source=True,
                observed_at=t0 + timedelta(hours=2, minutes=30),
            ),
        ),
    )
    relations = {edge.relation for edge in graph.edges}
    assert {
        "has_claim",
        "mentions",
        "attributed_to",
        "tracks_commitment",
        "committed_by",
        "verification_revision",
        "has_evidence",
    } <= relations
    assert any(node.node_type == "entity" and node.label == "Project Aurora" for node in graph.nodes)


def test_as_of_graph_does_not_leak_later_observations() -> None:
    t0 = datetime(2026, 8, 10, tzinfo=UTC)
    later = t0 + timedelta(days=2)
    graph = build_event_knowledge_graph(
        event_id="event-1",
        event_title="Event",
        event_observed_at=t0,
        claims=(
            KnowledgeClaimInput(
                claim_id="early",
                claim_text="Early claim.",
                observed_at=t0 + timedelta(hours=1),
                claim_type="other_factual",
                entities=(),
            ),
            KnowledgeClaimInput(
                claim_id="late",
                claim_text="Later claim.",
                observed_at=later,
                claim_type="other_factual",
                entities=(),
            ),
        ),
    )
    snapshot = graph_as_of(graph, t0 + timedelta(days=1))
    labels = {node.label for node in snapshot.nodes}
    assert "Early claim." in labels
    assert "Later claim." not in labels
