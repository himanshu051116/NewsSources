from types import SimpleNamespace
from uuid import uuid4
from pathlib import Path

from newsintel.application.articles.query_service import (
    _lineage_key_for_link,
    _near_duplicate_evidence,
    _ownership_reduced,
    _summarize_lineages,
)


def _link(*, lineage: str, url: str, independence: float = 0.8, **metadata):
    return SimpleNamespace(
        metadata_={"lineage_key": lineage, **metadata},
        evidence_article_id=None,
        source_url=url,
        source_type="news_report",
        relationship="support",
        independence_score=independence,
    )


def test_lineage_summary_deduplicates_repeated_links() -> None:
    claim_id = uuid4()
    links = [
        _link(lineage="publisher:wire", url="https://a.example/1", independence=0.9),
        _link(lineage="publisher:wire", url="https://b.example/2", independence=0.4),
        _link(lineage="publisher:independent", url="https://c.example/3", independence=0.8),
    ]
    rows = _summarize_lineages({claim_id: links})
    assert len(rows) == 2
    wire = next(row for row in rows if row.lineage_key == "publisher:wire")
    assert wire.link_count == 2
    assert wire.claim_count == 1
    assert wire.source_count == 2
    assert wire.max_independence_score == 0.9


def test_lineage_helpers_expose_independence_reductions() -> None:
    link = _link(
        lineage="publisher:x",
        url="https://x.example/story",
        shared_ownership_group=True,
        ownership_independence_cap=0.35,
        max_prior_lineage_similarity=0.91,
    )
    assert _lineage_key_for_link(link) == "publisher:x"
    assert _ownership_reduced(link) is True
    assert _near_duplicate_evidence(link) is True


def test_v113_ui_links_claims_to_investigation() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "newsintel" / "api" / "routes"
    search = (root / "search_dashboard.py").read_text()
    article = (root / "article_intelligence_dashboard.py").read_text()
    claim = (root / "claim_investigation_dashboard.py").read_text()
    assert "/claims/${{niEsc(item.id)}}/investigation" in search
    assert "Investigate claim" in article
    assert "Where the evidence came from" in claim
    assert "Recompute verification" in claim
