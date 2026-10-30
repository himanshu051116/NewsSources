"""In-process briefing assembly tests; exercise real business logic without external DB."""
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from newsintel.application.briefings.service import GroundedBriefingService


class _ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def scalars(self):
        return _ScalarResult(self.rows)

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class _ReplaySession:
    def __init__(self, event, rows):
        self.event = event
        self.results = iter(rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, _model, _id):
        return self.event

    async def execute(self, _statement):
        return _Result(next(self.results))


@pytest.mark.asyncio
@pytest.mark.parametrize("has_supporting_link", [True, False])
async def test_briefing_names_actual_report_and_cites_supporting_links(has_supporting_link):
    event_id, article_id, version_id, claim_id, evidence_id = (uuid4() for _ in range(5))
    now = datetime(2026, 10, 13, tzinfo=UTC)
    event = SimpleNamespace(
        id=event_id, title="Ministry publishes infrastructure update",
        lifecycle_status="developing", first_detected_at=now, last_material_change_at=now,
    )
    article = SimpleNamespace(id=article_id)
    version = SimpleNamespace(
        id=version_id, title="National plan completes five years",
        published_at=now, retrieved_at=now, final_url="https://example.org/release",
    )
    publisher = SimpleNamespace(name="Press Information Bureau")
    claim = SimpleNamespace(id=claim_id, claim_text="The ministry released its update.")
    verification = SimpleNamespace(claim_id=claim_id, label="supported", created_at=now)
    link = SimpleNamespace(
        id=evidence_id, claim_id=claim_id, relationship="support", source_type="official_document",
        source_url="https://example.org/official-source", retrieved_at=now,
    )
    query_rows = [
        [(article, version, publisher)],
        [claim],
        [verification],
        [link] if has_supporting_link else [],
        [],  # latest historical context
        [],  # confirmed corrections
    ]
    service = GroundedBriefingService(lambda: _ReplaySession(event, query_rows))
    payload, refs, evidence_hash = await service._build(event_id, version_id)
    assert payload["latest_reporting"][0]["title"] == version.title
    assert len(evidence_hash) == 64
    if has_supporting_link:
        assert len(payload["established_facts"]) == 1
        assert f"evidence_link:{evidence_id}" in payload["established_facts"][0]["evidence_ids"]
        assert any(r.get("url") == "https://example.org/official-source" for r in refs)
    else:
        assert payload["established_facts"] == []
        assert len(payload["unresolved_or_insufficient_evidence"]) == 1
        assert "evidence_trace_warning" in payload["unresolved_or_insufficient_evidence"][0]

@pytest.mark.asyncio
async def test_supported_claim_cites_support_before_more_recent_non_support_links():
    """The first eight citations must not crowd out the evidence for a supported verdict."""
    event_id, article_id, version_id, claim_id = (uuid4() for _ in range(4))
    now = datetime(2026, 10, 13, tzinfo=UTC)
    event = SimpleNamespace(
        id=event_id, title="Test event", lifecycle_status="developing",
        first_detected_at=now, last_material_change_at=now,
    )
    article = SimpleNamespace(id=article_id)
    version = SimpleNamespace(
        id=version_id, title="Story title", published_at=now,
        retrieved_at=now, final_url="https://example.org/story",
    )
    publisher = SimpleNamespace(name="Example Publisher")
    claim = SimpleNamespace(id=claim_id, claim_text="A report was published")
    verification = SimpleNamespace(claim_id=claim_id, label="supported", created_at=now)
    from datetime import timedelta
    evidence = [
        SimpleNamespace(
            id=uuid4(), claim_id=claim_id, relationship="context", source_type="news",
            source_url=f"https://example.org/context/{i}", retrieved_at=now+timedelta(seconds=i),
        )
        for i in range(12)
    ]
    support = SimpleNamespace(
        id=uuid4(), claim_id=claim_id, relationship="support", source_type="official_document",
        source_url="https://example.org/authority", retrieved_at=now-timedelta(days=1),
    )
    evidence.append(support)
    query_rows = [
        [(article, version, publisher)], [claim], [verification], evidence,
        [], [],
    ]
    service = GroundedBriefingService(lambda: _ReplaySession(event, query_rows))
    payload, refs, _ = await service._build(event_id, version_id)
    assert len(payload["established_facts"]) == 1
    sources = payload["established_facts"][0]["evidence_ids"]
    assert f"evidence_link:{support.id}" in sources
    assert len(sources) == 9  # claim plus the eight prioritized evidence links
    assert any(r.get("url") == "https://example.org/authority" for r in refs)
