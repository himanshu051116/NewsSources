import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from newsintel.domain.events.assignment import decide_event_assignment
from newsintel.domain.events.matching import ArticleEventProfile, EventReference, build_event_candidates


def test_event_pair_regression_benchmark_has_no_known_false_link_or_miss() -> None:
    cases = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "accuracy" / "event_pairs.json").read_text(
            encoding="utf-8"
        )
    )
    now = datetime(2026, 8, 24, 1, tzinfo=UTC)
    outcomes: list[tuple[str, bool, float]] = []

    for case in cases:
        incoming = ArticleEventProfile(
            title=case["left_title"],
            text=case["left_text"],
            published_at=now,
            observed_at=now,
        )
        reference = EventReference(
            event_id=uuid4(),
            title=case["right_title"],
            text=case["right_text"],
            first_detected_at=now - timedelta(hours=2),
            latest_observed_at=now - timedelta(hours=1),
        )
        candidate = build_event_candidates(incoming, [reference])[0]
        decision = decide_event_assignment([candidate])
        linked = decision.selected_event_id == reference.event_id
        outcomes.append((case["label"], linked, candidate.score))

    positives = [linked for label, linked, _score in outcomes if label == "same"]
    negatives = [linked for label, linked, _score in outcomes if label == "different"]

    assert positives and all(positives), outcomes
    assert negatives and not any(negatives), outcomes
