from datetime import UTC, datetime

from newsintel.domain.intelligence.knowledge_search import (
    KnowledgeSearchDocument,
    rank_knowledge_nodes,
)


def test_rank_prefers_label_match_over_payload_only_match() -> None:
    now = datetime.now(UTC)
    docs = (
        KnowledgeSearchDocument("a", "claim", "Inflation rose to seven percent", now, {}),
        KnowledgeSearchDocument("b", "claim", "Economic update", now, {"detail": "inflation increased"}),
    )
    hits = rank_knowledge_nodes("inflation", docs)
    assert [hit.node_key for hit in hits] == ["a", "b"]
    assert hits[0].score > hits[1].score


def test_node_type_filter_is_respected() -> None:
    now = datetime.now(UTC)
    docs = (
        KnowledgeSearchDocument("a", "claim", "Acme announced results", now, {}),
        KnowledgeSearchDocument("b", "entity", "Acme", now, {}),
    )
    hits = rank_knowledge_nodes("Acme", docs, node_types=("entity",))
    assert len(hits) == 1 and hits[0].node_key == "b"
