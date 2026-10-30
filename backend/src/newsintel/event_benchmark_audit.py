from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from dateutil import parser as date_parser

from newsintel.domain.events.assignment import decide_event_assignment
from newsintel.domain.events.benchmarking import EventLinkObservation, assess_event_link_benchmark
from newsintel.domain.events.matching import ArticleEventProfile, EventReference, build_event_candidates


def _default_input() -> Path:
    candidates = (
        Path.cwd() / "backend" / "tests" / "fixtures" / "accuracy" / "event_pairs.json",
        Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "accuracy" / "event_pairs.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _dt(value: object, fallback: datetime) -> datetime:
    if not value:
        return fallback
    parsed = date_parser.parse(str(value))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _assess(path: Path, candidate_threshold: float) -> tuple[dict[str, object], list[dict[str, object]]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("event benchmark input must be a JSON array")
    default_now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    observations: list[EventLinkObservation] = []
    details: list[dict[str, object]] = []
    for index, raw in enumerate(cases):
        if not isinstance(raw, dict):
            raise ValueError(f"benchmark case {index + 1} must be an object")
        label = str(raw.get("label") or "").strip().casefold()
        if label not in {"same", "different"}:
            raise ValueError(f"benchmark case {index + 1} label must be 'same' or 'different'")
        left_time = _dt(raw.get("left_published_at"), default_now)
        right_time = _dt(raw.get("right_observed_at"), left_time - timedelta(hours=1))
        incoming = ArticleEventProfile(
            title=str(raw.get("left_title") or ""),
            text=str(raw.get("left_text") or ""),
            published_at=left_time,
            observed_at=left_time,
        )
        reference = EventReference(
            event_id=uuid4(),
            title=str(raw.get("right_title") or ""),
            text=str(raw.get("right_text") or ""),
            first_detected_at=right_time,
            latest_observed_at=right_time,
        )
        candidate = build_event_candidates(incoming, [reference])[0]
        decision = decide_event_assignment([candidate], candidate_threshold=candidate_threshold)
        linked = decision.selected_event_id == reference.event_id
        key = str(raw.get("case_key") or f"case-{index + 1}")
        observation = EventLinkObservation(
            expected_same_event=label == "same",
            linked_same_event=linked,
            score=candidate.score,
            case_key=key,
            category=str(raw.get("category")) if raw.get("category") else None,
            language=str(raw.get("language")) if raw.get("language") else None,
        )
        observations.append(observation)
        details.append(
            {
                "case_key": key,
                "expected": label,
                "linked": linked,
                "score": round(candidate.score, 6),
                "assignment_state": decision.state.value,
                "passed": observation.expected_same_event == linked,
            }
        )
    assessment = assess_event_link_benchmark(tuple(observations), candidate_threshold=candidate_threshold)
    payload = {
        "benchmark_version": assessment.benchmark_version,
        "input": str(path),
        "candidate_threshold": candidate_threshold,
        "case_count": assessment.case_count,
        "positive_count": assessment.positive_count,
        "negative_count": assessment.negative_count,
        "true_positive": assessment.true_positive,
        "true_negative": assessment.true_negative,
        "false_positive": assessment.false_positive,
        "false_negative": assessment.false_negative,
        "accuracy": assessment.accuracy,
        "precision": assessment.precision,
        "recall": assessment.recall,
        "f1": assessment.f1,
        "false_link_rate": assessment.false_link_rate,
        "false_miss_rate": assessment.false_miss_rate,
        "mean_positive_score": assessment.mean_positive_score,
        "mean_negative_score": assessment.mean_negative_score,
        "min_positive_score": assessment.min_positive_score,
        "max_negative_score": assessment.max_negative_score,
        "positive_margin_to_threshold": assessment.positive_margin_to_threshold,
        "negative_margin_to_threshold": assessment.negative_margin_to_threshold,
        "failed_case_keys": list(assessment.failed_case_keys),
        "interpretation": assessment.interpretation,
    }
    return payload, details


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate adjudicated same-event/different-event pairs against the current event matcher."
    )
    parser.add_argument("--input", type=Path, default=None, help="JSON event-pair benchmark file.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--candidate-threshold", type=float, default=0.62)
    args = parser.parse_args()
    if not 0 <= args.candidate_threshold <= 1:
        parser.error("--candidate-threshold must be between 0 and 1")
    path = args.input or _default_input()
    if not path.exists():
        parser.error(f"benchmark input not found: {path}")
    assessment, details = _assess(path, args.candidate_threshold)
    if args.json:
        print(json.dumps({"assessment": assessment, "cases": details}, indent=2, ensure_ascii=False))
    else:
        print(f"Event benchmark: {path}")
        print(f"  Cases: {assessment['case_count']} ({assessment['positive_count']} same / {assessment['negative_count']} different)")
        print(f"  Precision: {assessment['precision']}  Recall: {assessment['recall']}  F1: {assessment['f1']}")
        print(f"  False-link rate: {assessment['false_link_rate']}  False-miss rate: {assessment['false_miss_rate']}")
        print(
            "  Score margins: "
            f"hardest positive={assessment['min_positive_score']} "
            f"hardest negative={assessment['max_negative_score']}"
        )
        failed = assessment["failed_case_keys"]
        if failed:
            print("  Failed cases:")
            for key in failed:
                print(f"    - {key}")
        else:
            print("  Failed cases: none")
        print("\nPer-case:")
        for item in details:
            mark = "PASS" if item["passed"] else "FAIL"
            print(
                f"  {mark:4}  {item['case_key']}: expected={item['expected']} "
                f"linked={item['linked']} score={item['score']}"
            )
        print("\nNote: metrics apply only to the adjudicated benchmark file; they are not a universal event-link accuracy claim.")
    raise SystemExit(1 if assessment["failed_case_keys"] else 0)


if __name__ == "__main__":
    run()
