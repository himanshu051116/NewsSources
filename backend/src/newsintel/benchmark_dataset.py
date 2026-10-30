from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from newsintel.core.config import get_settings
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.adjudication import (
    AdjudicationReview,
    assess_adjudication_agreement,
    decide_consensus,
)
from newsintel.domain.intelligence.claims import ClaimVerificationLabel
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimVerificationModel,
    VerificationBenchmarkAdjudicationModel,
    VerificationBenchmarkAgreementSnapshotModel,
    VerificationBenchmarkCandidateModel,
    VerificationBenchmarkCaseModel,
)
from newsintel.infrastructure.db.session import Database


def _json_default(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return]
    return str(value)


def _reviewer_hash(value: str) -> str:
    normalized = " ".join(value.strip().casefold().split())
    if len(normalized) < 2:
        raise ValueError("reviewer key must contain at least two characters")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _balanced(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Backward-compatible label round-robin sampler used by v1.8 tests/tools."""
    groups: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for row in rows:
        groups[str(row.get("predicted_label") or "unknown")].append(row)
    keys = sorted(groups)
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and keys:
        next_keys: list[str] = []
        for key in keys:
            bucket = groups[key]
            if bucket and len(selected) < limit:
                selected.append(bucket.popleft())
            if bucket:
                next_keys.append(key)
        keys = next_keys
    return selected


def _stratified(rows: list[dict[str, Any]], limit: int, seed: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        stratum = "|".join(
            (
                str(row.get("predicted_label") or "unknown"),
                str(row.get("language") or "unknown"),
                str(row.get("topic_key") or "unknown"),
            )
        )
        groups[stratum].append(row)
    queues: dict[str, deque[dict[str, Any]]] = {}
    for key, values in groups.items():
        values.sort(
            key=lambda item: hashlib.sha256(
                f"{seed}|{item.get('case_key')}".encode("utf-8")
            ).hexdigest()
        )
        queues[key] = deque(values)
    keys = sorted(queues)
    selected: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    while len(selected) < limit and keys:
        next_keys: list[str] = []
        deferred: list[tuple[str, dict[str, Any]]] = []
        for key in keys:
            bucket = queues[key]
            picked = None
            while bucket and picked is None:
                item = bucket.popleft()
                doc = str(item.get("source_document_key") or "")
                if doc and doc in seen_documents:
                    deferred.append((key, item))
                    continue
                picked = item
            if picked is not None and len(selected) < limit:
                selected.append(picked)
                doc = str(picked.get("source_document_key") or "")
                if doc:
                    seen_documents.add(doc)
            if bucket:
                next_keys.append(key)
        # Once source diversity has been exhausted, allow deferred same-document claims.
        if not next_keys and deferred and len(selected) < limit:
            for key, item in deferred:
                queues[key].append(item)
            keys = sorted({key for key, _ in deferred})
            seen_documents.clear()
        else:
            for key, item in deferred:
                queues[key].append(item)
                if key not in next_keys:
                    next_keys.append(key)
            keys = sorted(set(next_keys))
    return selected


async def _claim_candidates(*, recent_pool: int) -> list[dict[str, Any]]:
    db = Database(get_settings())
    try:
        async with db.session_factory() as session:
            base_rows = (
                await session.execute(
                    select(ArticleClaimModel, ArticleVersionModel, ArticleModel)
                    .join(ArticleVersionModel, ArticleVersionModel.id == ArticleClaimModel.article_version_id)
                    .join(ArticleModel, ArticleModel.id == ArticleClaimModel.article_id)
                    .order_by(ArticleClaimModel.created_at.desc())
                    .limit(recent_pool)
                )
            ).all()
            claim_ids = [claim.id for claim, _version, _article in base_rows]
            verifications = list(
                (
                    await session.scalars(
                        select(ClaimVerificationModel)
                        .where(ClaimVerificationModel.claim_id.in_(claim_ids))
                        .order_by(ClaimVerificationModel.claim_id, ClaimVerificationModel.created_at.desc())
                    )
                ).all()
            ) if claim_ids else []
        latest: dict[UUID, ClaimVerificationModel] = {}
        for item in verifications:
            latest.setdefault(item.claim_id, item)
        rows: list[dict[str, Any]] = []
        for claim, version, article in base_rows:
            verification = latest.get(claim.id)
            if verification is None:
                continue
            features = dict(claim.extraction_features or {})
            rows.append(
                {
                    "case_key": f"claim:{claim.id}",
                    "claim_id": str(claim.id),
                    "group_key": f"event:{article.event_id}",
                    "source_document_key": f"article-version:{version.content_sha256}",
                    "article_id": str(article.id),
                    "article_version_id": str(version.id),
                    "article_title": version.title,
                    "source_url": version.final_url or version.source_url,
                    "published_at": version.published_at,
                    "retrieved_at": version.retrieved_at,
                    "language": version.language or article.language,
                    "topic_key": features.get("topic_key") or features.get("claim_type"),
                    "claim_text": claim.claim_text,
                    "claim_type": features.get("claim_type"),
                    "checkability": features.get("checkability"),
                    "predicted_label": verification.label,
                    "predicted_confidence": verification.confidence_score or 0.0,
                    "prediction_methodology": verification.methodology_version,
                }
            )
        return rows
    finally:
        await db.dispose()


async def _sample(*, benchmark_set: str, split: str, limit: int, recent_pool: int, seed: str) -> int:
    rows = await _claim_candidates(recent_pool=recent_pool)
    db = Database(get_settings())
    now = datetime.now(UTC)
    try:
        async with db.session_factory() as session:
            candidate_rows = list((await session.scalars(select(VerificationBenchmarkCandidateModel).where(VerificationBenchmarkCandidateModel.benchmark_set == benchmark_set))).all())
            finalized_rows = list((await session.scalars(select(VerificationBenchmarkCaseModel).where(VerificationBenchmarkCaseModel.benchmark_set == benchmark_set))).all())
        existing = {item.case_key for item in candidate_rows}
        finalized = {item.case_key for item in finalized_rows if item.case_key}
        other_split_groups = {item.group_key for item in [*candidate_rows, *finalized_rows] if item.split != split and item.group_key}
        other_split_documents = {item.source_document_key for item in [*candidate_rows, *finalized_rows] if item.split != split and item.source_document_key}
        eligible = [
            row for row in rows
            if row["case_key"] not in existing
            and row["case_key"] not in finalized
            and row.get("group_key") not in other_split_groups
            and row.get("source_document_key") not in other_split_documents
        ]
        selected = _stratified(eligible, limit, seed)
        async with db.session_factory() as session, session.begin():
            for row in selected:
                session.add(
                    VerificationBenchmarkCandidateModel(
                        id=uuid7(),
                        benchmark_set=benchmark_set,
                        case_key=row["case_key"],
                        claim_id=UUID(row["claim_id"]),
                        group_key=row["group_key"],
                        source_document_key=row["source_document_key"],
                        split=split,
                        topic_key=row.get("topic_key"),
                        language=row.get("language"),
                        jurisdiction=None,
                        predicted_label=row["predicted_label"],
                        predicted_confidence=max(0.0, min(1.0, float(row["predicted_confidence"]))),
                        prediction_methodology=row["prediction_methodology"],
                        source_snapshot={
                            key: row.get(key)
                            for key in (
                                "article_id", "article_version_id", "article_title", "source_url",
                                "published_at", "retrieved_at", "claim_text", "claim_type", "checkability",
                            )
                        },
                        status="sampled",
                        created_at=now,
                        updated_at=now,
                    )
                )
            await session.flush()
        return len(selected)
    finally:
        await db.dispose()


def _blind_review_row(item: object) -> dict[str, object]:
    snap = dict(getattr(item, "source_snapshot", {}) or {})
    return {
        "candidate_id": str(getattr(item, "id")),
        "case_key": getattr(item, "case_key"),
        "article_title": snap.get("article_title"),
        "source_url": snap.get("source_url"),
        "published_at": snap.get("published_at"),
        "language": getattr(item, "language", None),
        "topic_key": getattr(item, "topic_key", None),
        "claim_text": snap.get("claim_text"),
        "claim_type": snap.get("claim_type"),
        "checkability": snap.get("checkability"),
        "adjudicated_label": "",
        "adjudication_source": "",
        "adjudication_notes": "",
    }


async def _review_sheet(path: Path, *, benchmark_set: str, reviewer_key: str, disputed_only: bool = False) -> int:
    reviewer_hash = _reviewer_hash(reviewer_key)
    db = Database(get_settings())
    try:
        async with db.session_factory() as session:
            candidates = list(
                (
                    await session.scalars(
                        select(VerificationBenchmarkCandidateModel)
                        .where(VerificationBenchmarkCandidateModel.benchmark_set == benchmark_set)
                        .order_by(VerificationBenchmarkCandidateModel.created_at, VerificationBenchmarkCandidateModel.case_key)
                    )
                ).all()
            )
            existing = set(
                (
                    await session.scalars(
                        select(VerificationBenchmarkAdjudicationModel.candidate_id).where(
                            VerificationBenchmarkAdjudicationModel.benchmark_set == benchmark_set,
                            VerificationBenchmarkAdjudicationModel.reviewer_key_hash == reviewer_hash,
                        )
                    )
                ).all()
            )
            all_reviews = list(
                (
                    await session.scalars(
                        select(VerificationBenchmarkAdjudicationModel).where(
                            VerificationBenchmarkAdjudicationModel.benchmark_set == benchmark_set
                        )
                    )
                ).all()
            )
        reviews_by_case: dict[str, list[VerificationBenchmarkAdjudicationModel]] = defaultdict(list)
        for review in all_reviews:
            reviews_by_case[review.case_key].append(review)
        rows = []
        for item in candidates:
            if item.id in existing or item.status == "finalized":
                continue
            if disputed_only:
                labels = {
                    review.adjudicated_label
                    for review in reviews_by_case.get(item.case_key, [])
                    if review.reviewer_role == "reviewer"
                }
                if len(labels) < 2:
                    continue
            rows.append(_blind_review_row(item))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
        return len(rows)
    finally:
        await db.dispose()


async def _review_import(path: Path, *, benchmark_set: str, reviewer_key: str, role: str) -> tuple[int, int]:
    reviewer_hash = _reviewer_hash(reviewer_key)
    role = "adjudicator" if role == "adjudicator" else "reviewer"
    allowed = {item.value for item in ClaimVerificationLabel}
    raw_rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    db = Database(get_settings())
    inserted = skipped = 0
    now = datetime.now(UTC)
    try:
        async with db.session_factory() as session, session.begin():
            candidate_ids = [UUID(str(row["candidate_id"])) for row in raw_rows if row.get("candidate_id")]
            candidates = list(
                (
                    await session.scalars(
                        select(VerificationBenchmarkCandidateModel).where(
                            VerificationBenchmarkCandidateModel.id.in_(candidate_ids),
                            VerificationBenchmarkCandidateModel.benchmark_set == benchmark_set,
                        )
                    )
                ).all()
            ) if candidate_ids else []
            by_id = {item.id: item for item in candidates}
            existing = set(
                (
                    await session.scalars(
                        select(VerificationBenchmarkAdjudicationModel.candidate_id).where(
                            VerificationBenchmarkAdjudicationModel.candidate_id.in_(candidate_ids),
                            VerificationBenchmarkAdjudicationModel.reviewer_key_hash == reviewer_hash,
                        )
                    )
                ).all()
            ) if candidate_ids else set()
            for line_no, row in enumerate(raw_rows, 1):
                candidate_id = UUID(str(row.get("candidate_id")))
                candidate = by_id.get(candidate_id)
                if candidate is None:
                    raise ValueError(f"line {line_no}: candidate does not belong to benchmark set")
                if candidate_id in existing:
                    skipped += 1
                    continue
                label = str(row.get("adjudicated_label") or "").strip().casefold()
                source = str(row.get("adjudication_source") or "").strip()
                if label not in allowed:
                    raise ValueError(f"line {line_no}: adjudicated_label must be one of {sorted(allowed)}")
                if not source:
                    raise ValueError(f"line {line_no}: adjudication_source is required")
                session.add(
                    VerificationBenchmarkAdjudicationModel(
                        id=uuid7(), candidate_id=candidate_id, benchmark_set=benchmark_set,
                        case_key=candidate.case_key, reviewer_key_hash=reviewer_hash, reviewer_role=role,
                        adjudicated_label=label, adjudication_source=source,
                        adjudication_notes=str(row.get("adjudication_notes") or "").strip() or None,
                        reviewed_at=now,
                        metadata_={"reviewer_key_fingerprint": reviewer_hash[:12], "imported_via": "newsintel.benchmark_dataset"},
                        created_at=now,
                    )
                )
                existing.add(candidate_id)
                inserted += 1
            await session.flush()
        return inserted, skipped
    finally:
        await db.dispose()


async def _agreement(benchmark_set: str, *, persist: bool = True) -> dict[str, Any]:
    db = Database(get_settings())
    try:
        async with db.session_factory() as session:
            rows = list((await session.scalars(select(VerificationBenchmarkAdjudicationModel).where(VerificationBenchmarkAdjudicationModel.benchmark_set == benchmark_set))).all())
        result = assess_adjudication_agreement(tuple(AdjudicationReview(item.case_key, item.reviewer_key_hash[:12], item.adjudicated_label, item.reviewer_role) for item in rows))
        if persist:
            now = datetime.now(UTC)
            async with db.session_factory() as session, session.begin():
                session.add(VerificationBenchmarkAgreementSnapshotModel(
                    id=uuid7(), benchmark_set=benchmark_set, methodology_version=result.methodology_version,
                    case_count=result.case_count, review_count=result.review_count,
                    multi_review_case_count=result.multi_review_case_count,
                    unanimous_case_count=result.unanimous_case_count,
                    disagreement_case_count=result.disagreement_case_count,
                    pairwise_agreement=result.pairwise_agreement,
                    krippendorff_alpha_nominal=result.krippendorff_alpha_nominal,
                    metadata_={"adjudicated_disagreement_count": result.adjudicated_disagreement_count, "label_counts": result.label_counts, "reviewer_counts": result.reviewer_counts, "interpretation": result.interpretation},
                    created_at=now,
                ))
                await session.flush()
        return {
            "methodology_version": result.methodology_version,
            "case_count": result.case_count,
            "review_count": result.review_count,
            "multi_review_case_count": result.multi_review_case_count,
            "unanimous_case_count": result.unanimous_case_count,
            "disagreement_case_count": result.disagreement_case_count,
            "adjudicated_disagreement_count": result.adjudicated_disagreement_count,
            "pairwise_agreement": result.pairwise_agreement,
            "krippendorff_alpha_nominal": result.krippendorff_alpha_nominal,
            "label_counts": result.label_counts,
            "reviewer_counts": result.reviewer_counts,
            "interpretation": result.interpretation,
        }
    finally:
        await db.dispose()


async def _finalize(benchmark_set: str) -> tuple[int, int, int]:
    db = Database(get_settings())
    finalized = disagreements = pending = 0
    now = datetime.now(UTC)
    try:
        async with db.session_factory() as session, session.begin():
            candidates = list((await session.scalars(select(VerificationBenchmarkCandidateModel).where(VerificationBenchmarkCandidateModel.benchmark_set == benchmark_set))).all())
            reviews = list((await session.scalars(select(VerificationBenchmarkAdjudicationModel).where(VerificationBenchmarkAdjudicationModel.benchmark_set == benchmark_set))).all())
            existing_keys = set((await session.scalars(select(VerificationBenchmarkCaseModel.case_key).where(VerificationBenchmarkCaseModel.benchmark_set == benchmark_set))).all())
            by_case: dict[str, list[VerificationBenchmarkAdjudicationModel]] = defaultdict(list)
            for review in reviews:
                by_case[review.case_key].append(review)
            for candidate in candidates:
                if candidate.case_key in existing_keys:
                    candidate.status = "finalized"
                    continue
                case_reviews = by_case.get(candidate.case_key, [])
                decision = decide_consensus(candidate.case_key, tuple(AdjudicationReview(item.case_key, item.reviewer_key_hash[:12], item.adjudicated_label, item.reviewer_role) for item in case_reviews))
                if decision.label is None:
                    candidate.status = "disagreement" if decision.state == "disagreement" else "pending_review"
                    disagreements += decision.state == "disagreement"
                    pending += decision.state != "disagreement"
                    candidate.updated_at = now
                    continue
                reviewer_sources = [item.adjudication_source for item in case_reviews]
                snap = dict(candidate.source_snapshot or {})
                session.add(VerificationBenchmarkCaseModel(
                    id=uuid7(), claim_id=candidate.claim_id, benchmark_set=benchmark_set,
                    case_key=candidate.case_key, group_key=candidate.group_key,
                    source_document_key=candidate.source_document_key, split=candidate.split,
                    topic_key=candidate.topic_key, language=candidate.language, jurisdiction=candidate.jurisdiction,
                    predicted_label=candidate.predicted_label, predicted_confidence=candidate.predicted_confidence,
                    adjudicated_label=decision.label,
                    adjudication_source="; ".join(dict.fromkeys(reviewer_sources))[:200],
                    adjudicator_count=len(case_reviews), adjudicated_at=now, weight=1.0,
                    metadata_={**snap, "prediction_methodology_at_sampling": candidate.prediction_methodology,
                               "consensus_state": decision.state, "reviewer_labels": list(decision.reviewer_labels),
                               "adjudicator_label": decision.adjudicator_label,
                               "adjudication_blind": True},
                    created_at=now,
                ))
                candidate.status = "finalized"
                candidate.updated_at = now
                existing_keys.add(candidate.case_key)
                finalized += 1
            await session.flush()
        await _agreement(benchmark_set, persist=True)
        return finalized, disagreements, pending
    finally:
        await db.dispose()


# Legacy export/import remain for backward compatibility. They are intentionally explicit because
# they expose the prediction and should not be used for a new independent held-out benchmark.
async def _legacy_export(path: Path, *, limit: int, recent_pool: int) -> int:
    rows = await _claim_candidates(recent_pool=recent_pool)
    selected = _stratified(rows, limit, "legacy")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in selected:
            handle.write(json.dumps({**row, "adjudicated_label": "", "adjudication_source": "", "adjudicator_count": 1, "adjudication_notes": "", "weight": 1.0}, ensure_ascii=False, default=_json_default) + "\n")
    return len(selected)


async def _legacy_import(path: Path, *, benchmark_set: str, split: str) -> tuple[int, int]:
    allowed = {item.value for item in ClaimVerificationLabel}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    db = Database(get_settings())
    inserted = skipped = 0
    now = datetime.now(UTC)
    try:
        async with db.session_factory() as session, session.begin():
            existing = set((await session.scalars(select(VerificationBenchmarkCaseModel.case_key).where(VerificationBenchmarkCaseModel.benchmark_set == benchmark_set))).all())
            for line_no, item in enumerate(rows, 1):
                label = str(item.get("adjudicated_label") or "").strip().casefold()
                source = str(item.get("adjudication_source") or "").strip()
                if label not in allowed or not source:
                    raise ValueError(f"line {line_no}: completed adjudication label and source are required")
                case_key = str(item.get("case_key") or "").strip() or None
                if case_key and case_key in existing:
                    skipped += 1
                    continue
                session.add(VerificationBenchmarkCaseModel(
                    id=uuid7(), claim_id=UUID(str(item["claim_id"])) if item.get("claim_id") else None,
                    benchmark_set=benchmark_set, case_key=case_key,
                    group_key=str(item.get("group_key") or "").strip() or None,
                    source_document_key=str(item.get("source_document_key") or "").strip() or None,
                    split=split, topic_key=str(item.get("topic_key") or "").strip() or None,
                    language=str(item.get("language") or "").strip() or None,
                    jurisdiction=str(item.get("jurisdiction") or "").strip() or None,
                    predicted_label=str(item.get("predicted_label") or "").strip().casefold(),
                    predicted_confidence=max(0.0, min(1.0, float(item.get("predicted_confidence") or 0.0))),
                    adjudicated_label=label, adjudication_source=source,
                    adjudicator_count=max(1, int(item.get("adjudicator_count") or 1)), adjudicated_at=now,
                    weight=max(0.000001, float(item.get("weight") or 1.0)),
                    metadata_={"article_id": item.get("article_id"), "article_version_id": item.get("article_version_id"), "article_title": item.get("article_title"), "source_url": item.get("source_url"), "claim_text": item.get("claim_text"), "claim_type": item.get("claim_type"), "checkability": item.get("checkability"), "methodology_version_at_export": item.get("prediction_methodology") or item.get("methodology_version"), "adjudication_notes": item.get("adjudication_notes"), "imported_via": "legacy_visible_prediction_workflow"},
                    created_at=now,
                ))
                if case_key: existing.add(case_key)
                inserted += 1
            await session.flush()
        return inserted, skipped
    finally:
        await db.dispose()


def run() -> None:
    parser = argparse.ArgumentParser(description="Build and adjudicate verification benchmarks without leaking model predictions to independent reviewers.")
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="Create a deterministic stratified benchmark candidate sample in the database.")
    sample.add_argument("--benchmark-set", required=True)
    sample.add_argument("--split", default="test")
    sample.add_argument("--limit", type=int, default=200)
    sample.add_argument("--recent-pool", type=int, default=5000)
    sample.add_argument("--seed", default="20260824")

    sheet = sub.add_parser("review-sheet", help="Export a blind review worksheet. Model prediction/confidence are omitted.")
    sheet.add_argument("--benchmark-set", required=True)
    sheet.add_argument("--reviewer-key", required=True)
    sheet.add_argument("--output", type=Path, required=True)

    adjud_sheet = sub.add_parser("adjudicator-sheet", help="Export only cases where independent reviewers disagree.")
    adjud_sheet.add_argument("--benchmark-set", required=True)
    adjud_sheet.add_argument("--reviewer-key", required=True)
    adjud_sheet.add_argument("--output", type=Path, required=True)

    review_import = sub.add_parser("review-import", help="Import a completed blind review worksheet.")
    review_import.add_argument("--benchmark-set", required=True)
    review_import.add_argument("--reviewer-key", required=True)
    review_import.add_argument("--role", choices=("reviewer", "adjudicator"), default="reviewer")
    review_import.add_argument("--input", type=Path, required=True)

    agreement = sub.add_parser("agreement", help="Measure independent human-review agreement for a benchmark set.")
    agreement.add_argument("--benchmark-set", required=True)
    agreement.add_argument("--json", action="store_true")

    finalize = sub.add_parser("finalize", help="Finalize unanimous double-review cases and separately adjudicated disagreements.")
    finalize.add_argument("--benchmark-set", required=True)

    legacy_export = sub.add_parser("export", help="LEGACY: export a prediction-visible worksheet. Prefer sample + review-sheet.")
    legacy_export.add_argument("--output", type=Path, required=True)
    legacy_export.add_argument("--limit", type=int, default=200)
    legacy_export.add_argument("--recent-pool", type=int, default=3000)
    legacy_import = sub.add_parser("import", help="LEGACY: import a prediction-visible worksheet.")
    legacy_import.add_argument("--input", type=Path, required=True)
    legacy_import.add_argument("--benchmark-set", required=True)
    legacy_import.add_argument("--split", default="test")

    args = parser.parse_args()
    if args.command == "sample":
        count = asyncio.run(_sample(benchmark_set=args.benchmark_set, split=args.split, limit=args.limit, recent_pool=args.recent_pool, seed=args.seed))
        print(f"Sampled {count} blind adjudication candidates into '{args.benchmark_set}'.")
    elif args.command in {"review-sheet", "adjudicator-sheet"}:
        count = asyncio.run(_review_sheet(args.output, benchmark_set=args.benchmark_set, reviewer_key=args.reviewer_key, disputed_only=args.command == "adjudicator-sheet"))
        print(f"Exported {count} blind review cases to {args.output}")
        print("The worksheet intentionally omits the system prediction and confidence to reduce reviewer anchoring.")
    elif args.command == "review-import":
        if not args.input.exists(): parser.error(f"input file not found: {args.input}")
        inserted, skipped = asyncio.run(_review_import(args.input, benchmark_set=args.benchmark_set, reviewer_key=args.reviewer_key, role=args.role))
        print(f"Imported {inserted} reviews ({skipped} already present).")
    elif args.command == "agreement":
        result = asyncio.run(_agreement(args.benchmark_set, persist=True))
        if args.json: print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Cases: {result['case_count']}  Reviews: {result['review_count']}")
            print(f"Multi-review: {result['multi_review_case_count']}  Unanimous: {result['unanimous_case_count']}  Disagreements: {result['disagreement_case_count']}")
            print(f"Pairwise agreement: {result['pairwise_agreement']}  Krippendorff alpha: {result['krippendorff_alpha_nominal']}")
    elif args.command == "finalize":
        finalized, disagreements, pending = asyncio.run(_finalize(args.benchmark_set))
        print(f"Finalized {finalized}; disagreements awaiting adjudication: {disagreements}; insufficient-review cases: {pending}.")
    elif args.command == "export":
        print("WARNING: legacy export exposes model predictions and can anchor reviewers. Prefer the blind workflow.")
        count = asyncio.run(_legacy_export(args.output, limit=args.limit, recent_pool=args.recent_pool))
        print(f"Exported {count} legacy adjudication candidates to {args.output}")
    else:
        inserted, skipped = asyncio.run(_legacy_import(args.input, benchmark_set=args.benchmark_set, split=args.split))
        print(f"Imported {inserted} cases ({skipped} duplicates skipped).")


if __name__ == "__main__":
    run()
