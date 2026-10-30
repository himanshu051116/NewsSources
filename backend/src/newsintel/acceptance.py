from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import httpx
from sqlalchemy import and_, func, select

from newsintel.core.config import Settings
from newsintel.infrastructure.db.models import (
    ArticleHistoricalContextModel,
    ArticleModel,
    ArticleVersionModel,
    DiscoveryChannelModel,
    EventBriefingModel,
    PublisherModel,
    UrlCandidateModel,
)
from newsintel.infrastructure.db.session import Database


@dataclass(frozen=True)
class AcceptanceThresholds:
    api_availability_min: float = 0.995
    extraction_success_min: float = 0.95
    discovery_p95_max_seconds: float = 120.0
    historical_completion_min: float = 0.95
    historical_slo_seconds: int = 600
    briefing_completion_min: float = 0.95
    briefing_slo_seconds: int = 720
    stale_lease_multiplier: float = 2.0


_PROFILE_HOURS = {"24h": 24.0, "72h": 72.0, "7d": 168.0}
_PROFILE_MIN_SAMPLES = {
    "24h": {"extraction": 20, "discovery": 10, "historical": 10, "briefing": 5},
    "72h": {"extraction": 50, "discovery": 20, "historical": 25, "briefing": 10},
    "7d": {"extraction": 100, "discovery": 50, "historical": 50, "briefing": 25},
}


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def _ratio(num: int, den: int) -> float | None:
    return None if den <= 0 else num / den


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def _seconds(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}s"


async def collect_snapshot(
    *,
    settings: Settings,
    trial_start: datetime,
    base_url: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    database = Database(settings)
    try:
        api_live, api_ready = await _probe_api(base_url or settings.public_base_url)
        async with database.session_factory() as session:
            terminal_base = and_(
                UrlCandidateModel.first_discovered_at.is_not(None),
                UrlCandidateModel.first_discovered_at >= trial_start,
                UrlCandidateModel.first_discovered_at <= now,
            )
            processed = int(
                await session.scalar(
                    select(func.count(UrlCandidateModel.id)).where(
                        terminal_base,
                        UrlCandidateModel.state == "processed",
                    )
                )
                or 0
            )
            failed = int(
                await session.scalar(
                    select(func.count(UrlCandidateModel.id)).where(
                        terminal_base,
                        UrlCandidateModel.state == "failed",
                    )
                )
                or 0
            )
            rejected = int(
                await session.scalar(
                    select(func.count(UrlCandidateModel.id)).where(
                        terminal_base,
                        UrlCandidateModel.state == "rejected",
                    )
                )
                or 0
            )
            pending = int(
                await session.scalar(
                    select(func.count(UrlCandidateModel.id)).where(
                        terminal_base,
                        UrlCandidateModel.state.in_(["ready", "leased", "retry"]),
                    )
                )
                or 0
            )

            article_count = int(
                await session.scalar(
                    select(func.count(ArticleModel.id)).where(
                        ArticleModel.first_observed_at >= trial_start,
                        ArticleModel.first_observed_at <= now,
                    )
                )
                or 0
            )

            latency_expr = func.extract(
                "epoch",
                UrlCandidateModel.first_discovered_at - UrlCandidateModel.published_at,
            )
            discovery_filter = and_(
                UrlCandidateModel.first_discovered_at.is_not(None),
                UrlCandidateModel.published_at.is_not(None),
                UrlCandidateModel.first_discovered_at >= trial_start,
                UrlCandidateModel.first_discovered_at <= now,
                UrlCandidateModel.first_discovered_at >= UrlCandidateModel.published_at,
            )
            discovery_samples = int(
                await session.scalar(
                    select(func.count(UrlCandidateModel.id)).where(discovery_filter)
                )
                or 0
            )
            discovery_p95 = await session.scalar(
                select(func.percentile_cont(0.95).within_group(latency_expr)).where(
                    discovery_filter
                )
            )

            historical_cutoff = now - timedelta(seconds=600)
            historical_eligible = int(
                await session.scalar(
                    select(func.count(ArticleVersionModel.id)).where(
                        ArticleVersionModel.created_at >= trial_start,
                        ArticleVersionModel.created_at <= historical_cutoff,
                    )
                )
                or 0
            )
            historical_on_time = int(
                await session.scalar(
                    select(func.count(ArticleVersionModel.id))
                    .select_from(ArticleVersionModel)
                    .join(
                        ArticleHistoricalContextModel,
                        ArticleHistoricalContextModel.article_version_id == ArticleVersionModel.id,
                    )
                    .where(
                        ArticleVersionModel.created_at >= trial_start,
                        ArticleVersionModel.created_at <= historical_cutoff,
                        ArticleHistoricalContextModel.generated_at
                        <= ArticleVersionModel.created_at + timedelta(seconds=600),
                    )
                )
                or 0
            )

            briefing_cutoff = now - timedelta(seconds=720)
            eligible_versions = (
                select(
                    ArticleVersionModel.id.label("version_id"),
                    ArticleVersionModel.created_at.label("committed_at"),
                    ArticleModel.event_id.label("event_id"),
                )
                .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                .where(
                    ArticleVersionModel.created_at >= trial_start,
                    ArticleVersionModel.created_at <= briefing_cutoff,
                )
                .subquery()
            )
            briefing_eligible = int(
                await session.scalar(select(func.count()).select_from(eligible_versions)) or 0
            )
            briefing_on_time = int(
                await session.scalar(
                    select(func.count(func.distinct(eligible_versions.c.version_id)))
                    .select_from(eligible_versions)
                    .join(
                        EventBriefingModel,
                        and_(
                            EventBriefingModel.event_id == eligible_versions.c.event_id,
                            EventBriefingModel.generated_at >= eligible_versions.c.committed_at,
                            EventBriefingModel.generated_at
                            <= eligible_versions.c.committed_at + timedelta(seconds=720),
                        ),
                    )
                )
                or 0
            )

            stale_poll_max = await session.scalar(
                select(
                    func.max(func.extract("epoch", now - DiscoveryChannelModel.lease_expires_at))
                ).where(
                    DiscoveryChannelModel.lease_owner.is_not(None),
                    DiscoveryChannelModel.lease_expires_at.is_not(None),
                    DiscoveryChannelModel.lease_expires_at < now,
                )
            )
            stale_article_max = await session.scalar(
                select(
                    func.max(func.extract("epoch", now - UrlCandidateModel.lease_expires_at))
                ).where(
                    UrlCandidateModel.state == "leased",
                    UrlCandidateModel.lease_expires_at.is_not(None),
                    UrlCandidateModel.lease_expires_at < now,
                )
            )

            publisher_rows = (
                await session.execute(
                    select(
                        PublisherModel.name,
                        func.count(UrlCandidateModel.id).filter(
                            UrlCandidateModel.state == "processed"
                        ).label("processed"),
                        func.count(UrlCandidateModel.id).filter(
                            UrlCandidateModel.state == "failed"
                        ).label("failed"),
                    )
                    .select_from(PublisherModel)
                    .join(
                        UrlCandidateModel,
                        UrlCandidateModel.publisher_id == PublisherModel.id,
                    )
                    .where(
                        UrlCandidateModel.first_discovered_at.is_not(None),
                        UrlCandidateModel.first_discovered_at >= trial_start,
                        UrlCandidateModel.first_discovered_at <= now,
                    )
                    .group_by(PublisherModel.id, PublisherModel.name)
                    .order_by(PublisherModel.name.asc())
                )
            ).all()

        return {
            "schema": "newsintel-acceptance-snapshot-v1",
            "trial_start": _iso(trial_start),
            "captured_at": _iso(now),
            "elapsed_seconds": max(0.0, (now - trial_start).total_seconds()),
            "api_live": api_live,
            "api_ready": api_ready,
            "articles_observed": article_count,
            "extraction": {
                "processed": processed,
                "failed": failed,
                "rejected": rejected,
                "pending": pending,
                "eligible_terminal": processed + failed,
                "success_rate": _ratio(processed, processed + failed),
            },
            "discovery": {
                "timestamped_samples": discovery_samples,
                "p95_seconds": float(discovery_p95) if discovery_p95 is not None else None,
            },
            "historical": {
                "eligible_versions": historical_eligible,
                "completed_within_10m": historical_on_time,
                "completion_rate_within_10m": _ratio(historical_on_time, historical_eligible),
            },
            "briefings": {
                "eligible_versions": briefing_eligible,
                "covered_within_12m": briefing_on_time,
                "completion_rate_within_12m": _ratio(briefing_on_time, briefing_eligible),
            },
            "leases": {
                "stale_poll_max_seconds": float(stale_poll_max or 0.0),
                "stale_article_max_seconds": float(stale_article_max or 0.0),
                "poll_lease_seconds": settings.poll_worker_lease_seconds,
                "article_lease_seconds": settings.article_worker_lease_seconds,
            },
            "publishers": [
                {
                    "name": name,
                    "processed": int(pub_processed or 0),
                    "failed": int(pub_failed or 0),
                    "success_rate": _ratio(
                        int(pub_processed or 0),
                        int(pub_processed or 0) + int(pub_failed or 0),
                    ),
                }
                for name, pub_processed, pub_failed in publisher_rows
            ],
        }
    finally:
        await database.dispose()


async def _probe_api(base_url: str) -> tuple[bool, bool]:
    base = base_url.rstrip("/")
    timeout = httpx.Timeout(5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        live = await _probe(client, f"{base}/api/v1/health/live")
        ready = await _probe(client, f"{base}/api/v1/health/ready")
    return live, ready


async def _probe(client: httpx.AsyncClient, url: str) -> bool:
    try:
        response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def evaluate_samples(
    samples: list[dict[str, Any]],
    *,
    profile: str,
    thresholds: AcceptanceThresholds | None = None,
    min_samples: dict[str, int] | None = None,
) -> dict[str, Any]:
    if profile not in _PROFILE_HOURS:
        raise ValueError(f"unknown acceptance profile: {profile}")
    if not samples:
        raise ValueError("acceptance input contains no samples")
    t = thresholds or AcceptanceThresholds()
    mins = dict(_PROFILE_MIN_SAMPLES[profile])
    if min_samples:
        mins.update(min_samples)
    ordered = sorted(samples, key=lambda item: str(item.get("captured_at") or ""))
    monitored = [
        item
        for item in ordered
        if item.get("schema")
        in {"newsintel-acceptance-snapshot-v1", "newsintel-acceptance-snapshot-error-v1"}
    ]
    valid = [item for item in monitored if item.get("schema") == "newsintel-acceptance-snapshot-v1"]
    if not valid:
        raise ValueError("acceptance input contains no valid News Intelligence snapshots")
    first, final = valid[0], valid[-1]
    last_observation = monitored[-1] if monitored else final
    elapsed_hours = float(last_observation.get("elapsed_seconds") or 0.0) / 3600.0
    readiness = sum(1 for item in monitored if item.get("api_ready") is True) / len(monitored)
    liveness = sum(1 for item in monitored if item.get("api_live") is True) / len(monitored)

    checks: list[dict[str, Any]] = []

    def add(
        name: str,
        state: str,
        *,
        measured: Any,
        target: str,
        detail: str,
    ) -> None:
        checks.append(
            {
                "name": name,
                "state": state,
                "measured": measured,
                "target": target,
                "detail": detail,
            }
        )

    target_hours = _PROFILE_HOURS[profile]
    add(
        "trial_duration",
        "PASS" if elapsed_hours >= target_hours * 0.995 else "BLOCKED",
        measured=round(elapsed_hours, 3),
        target=f">= {target_hours:g} hours",
        detail="The trial must run for essentially the full requested acceptance window.",
    )
    add(
        "api_readiness",
        "PASS" if readiness >= t.api_availability_min else "FAIL",
        measured=round(readiness, 6),
        target=f">= {t.api_availability_min:.3f}",
        detail=f"Ready samples {sum(1 for x in valid if x.get('api_ready') is True)}/{len(valid)}; liveness={liveness:.6f}.",
    )

    extraction = final.get("extraction") or {}
    extraction_n = int(extraction.get("eligible_terminal") or 0)
    extraction_rate = extraction.get("success_rate")
    if extraction_n < mins["extraction"]:
        state = "BLOCKED"
    else:
        state = "PASS" if extraction_rate is not None and extraction_rate >= t.extraction_success_min else "FAIL"
    add(
        "terminal_extraction_success",
        state,
        measured={"samples": extraction_n, "rate": extraction_rate},
        target=f">= {t.extraction_success_min:.2f} with >= {mins['extraction']} terminal candidates",
        detail="Candidate-level final outcome; retries do not inflate the denominator and rejected non-articles are excluded.",
    )

    discovery = final.get("discovery") or {}
    discovery_n = int(discovery.get("timestamped_samples") or 0)
    discovery_p95 = discovery.get("p95_seconds")
    if discovery_n < mins["discovery"]:
        state = "BLOCKED"
    else:
        state = "PASS" if discovery_p95 is not None and discovery_p95 <= t.discovery_p95_max_seconds else "FAIL"
    add(
        "publication_to_discovery_p95",
        state,
        measured={"samples": discovery_n, "p95_seconds": discovery_p95},
        target=f"<= {t.discovery_p95_max_seconds:.0f}s with >= {mins['discovery']} timestamped candidates",
        detail="Measured only when a trustworthy publisher publication timestamp is stored; this is not network fetch latency.",
    )

    historical = final.get("historical") or {}
    historical_n = int(historical.get("eligible_versions") or 0)
    historical_rate = historical.get("completion_rate_within_10m")
    if historical_n < mins["historical"]:
        state = "BLOCKED"
    else:
        state = "PASS" if historical_rate is not None and historical_rate >= t.historical_completion_min else "FAIL"
    add(
        "historical_enrichment_within_10m",
        state,
        measured={"eligible_versions": historical_n, "rate": historical_rate},
        target=f">= {t.historical_completion_min:.2f} with >= {mins['historical']} eligible versions",
        detail="Only versions old enough to have consumed the entire 10-minute SLO window are included.",
    )

    briefings = final.get("briefings") or {}
    briefing_n = int(briefings.get("eligible_versions") or 0)
    briefing_rate = briefings.get("completion_rate_within_12m")
    if briefing_n < mins["briefing"]:
        state = "BLOCKED"
    else:
        state = "PASS" if briefing_rate is not None and briefing_rate >= t.briefing_completion_min else "FAIL"
    add(
        "grounded_briefing_within_12m",
        state,
        measured={"eligible_versions": briefing_n, "rate": briefing_rate},
        target=f">= {t.briefing_completion_min:.2f} with >= {mins['briefing']} eligible versions",
        detail="A version is covered when its event receives a grounded briefing after that commit and within 12 minutes.",
    )

    max_poll_stale = max(float((item.get("leases") or {}).get("stale_poll_max_seconds") or 0.0) for item in valid)
    max_article_stale = max(float((item.get("leases") or {}).get("stale_article_max_seconds") or 0.0) for item in valid)
    final_leases = final.get("leases") or {}
    poll_limit = float(final_leases.get("poll_lease_seconds") or 0) * t.stale_lease_multiplier
    article_limit = float(final_leases.get("article_lease_seconds") or 0) * t.stale_lease_multiplier
    stale_ok = (max_poll_stale <= poll_limit) and (max_article_stale <= article_limit)
    add(
        "persistent_stale_worker_leases",
        "PASS" if stale_ok else "FAIL",
        measured={
            "max_poll_stale_seconds": max_poll_stale,
            "max_article_stale_seconds": max_article_stale,
        },
        target=f"poll <= {poll_limit:.0f}s and article <= {article_limit:.0f}s",
        detail="Uses the worst observed expired-lease age across the sampled trial.",
    )

    states = {item["state"] for item in checks}
    overall = "FAIL" if "FAIL" in states else "BLOCKED" if "BLOCKED" in states else "PASS"
    return {
        "schema": "newsintel-acceptance-report-v1",
        "profile": profile,
        "state": overall,
        "sample_count": len(monitored),
        "valid_snapshot_count": len(valid),
        "error_snapshot_count": len(monitored) - len(valid),
        "trial_start": first.get("trial_start"),
        "first_sample_at": first.get("captured_at"),
        "last_sample_at": final.get("captured_at"),
        "elapsed_hours": round(elapsed_hours, 6),
        "checks": checks,
        "final_snapshot": final,
        "guardrail": (
            "PASS means the configured operational targets were observed in this trial. It does not establish content rights, factual-truth accuracy, or universal publisher coverage. BLOCKED means the trial duration or evidence volume was insufficient."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# News Intelligence Production Acceptance Report",
        "",
        f"**Profile:** {report['profile']}",
        f"**State:** {report['state']}",
        f"**Samples:** {report['sample_count']}",
        f"**Elapsed:** {report['elapsed_hours']:.2f} hours",
        f"**Trial start:** {report.get('trial_start') or 'unknown'}",
        f"**Last sample:** {report.get('last_sample_at') or 'unknown'}",
        "",
        "| Check | State | Measured | Target |",
        "|---|---:|---|---|",
    ]
    for check in report["checks"]:
        measured = _measured_text(check["measured"])
        lines.append(
            f"| {check['name']} | **{check['state']}** | {measured} | {check['target']} |"
        )
    lines.extend(["", "## Check notes", ""])
    for check in report["checks"]:
        lines.append(f"- **{check['name']}** — {check['detail']}")
    final = report.get("final_snapshot") or {}
    lines.extend(["", "## Final trial counters", ""])
    lines.append(f"- Articles observed: {final.get('articles_observed', 0)}")
    ext = final.get("extraction") or {}
    lines.append(
        f"- Extraction terminal outcomes: {ext.get('processed', 0)} processed / {ext.get('failed', 0)} failed / {ext.get('rejected', 0)} rejected / {ext.get('pending', 0)} pending"
    )
    lines.append(f"- Extraction success: {_percent(ext.get('success_rate'))}")
    disc = final.get("discovery") or {}
    lines.append(
        f"- Publication→discovery p95: {_seconds(disc.get('p95_seconds'))} across {disc.get('timestamped_samples', 0)} timestamped candidates"
    )
    hist = final.get("historical") or {}
    lines.append(f"- Historical completion within 10m: {_percent(hist.get('completion_rate_within_10m'))}")
    brief = final.get("briefings") or {}
    lines.append(f"- Briefing completion within 12m: {_percent(brief.get('completion_rate_within_12m'))}")
    publishers = final.get("publishers") or []
    if publishers:
        lines.extend(["", "## Publisher terminal outcomes", "", "| Publisher | Processed | Failed | Success |", "|---|---:|---:|---:|"])
        for publisher in publishers:
            lines.append(
                f"| {publisher['name']} | {publisher['processed']} | {publisher['failed']} | {_percent(publisher.get('success_rate'))} |"
            )
    lines.extend(["", f"> {report['guardrail']}", ""])
    return "\n".join(lines)


def _measured_text(value: Any) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            if isinstance(item, float) and 0 <= item <= 1 and "seconds" not in key:
                rendered = _percent(item)
            elif isinstance(item, float):
                rendered = f"{item:.2f}"
            else:
                rendered = str(item)
            parts.append(f"{key}={rendered}")
        return "; ".join(parts)
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def load_samples(path: str) -> list[dict[str, Any]]:
    handle = sys.stdin if path == "-" else Path(path).open("r", encoding="utf-8")
    close = handle is not sys.stdin
    try:
        rows = []
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows
    finally:
        if close:
            handle.close()


async def monitor(
    *,
    trial_start: datetime,
    duration_seconds: int,
    interval_seconds: int,
    base_url: str | None,
) -> None:
    settings = Settings()
    deadline = datetime.now(UTC) + timedelta(seconds=duration_seconds)
    while True:
        try:
            snapshot = await collect_snapshot(
                settings=settings,
                trial_start=trial_start,
                base_url=base_url,
            )
            print(json.dumps(snapshot, separators=(",", ":"), default=str), flush=True)
        except Exception as exc:
            now = datetime.now(UTC)
            print(
                json.dumps(
                    {
                        "schema": "newsintel-acceptance-snapshot-error-v1",
                        "trial_start": _iso(trial_start),
                        "captured_at": _iso(now),
                        "elapsed_seconds": max(0.0, (now - trial_start).total_seconds()),
                        "api_live": False,
                        "api_ready": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:1000],
                    },
                    separators=(",", ":"),
                ),
                flush=True,
            )
        if datetime.now(UTC) >= deadline:
            break
        await asyncio.sleep(interval_seconds)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure and evaluate News Intelligence live production acceptance trials."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="Emit one cumulative acceptance snapshot as JSON.")
    snapshot.add_argument("--trial-start", required=True, help="UTC/offset ISO-8601 trial start.")
    snapshot.add_argument("--base-url", default=None)

    monitor_cmd = sub.add_parser("monitor", help="Emit NDJSON snapshots for a timed trial.")
    monitor_cmd.add_argument("--trial-start", default=None, help="Defaults to monitor start time.")
    monitor_cmd.add_argument("--duration-hours", type=float, required=True)
    monitor_cmd.add_argument("--interval-seconds", type=int, default=60)
    monitor_cmd.add_argument("--base-url", default=None)

    evaluate = sub.add_parser("evaluate", help="Evaluate an NDJSON trial against launch SLOs.")
    evaluate.add_argument("--input", default="-", help="NDJSON file or - for stdin.")
    evaluate.add_argument("--profile", choices=sorted(_PROFILE_HOURS), required=True)
    evaluate.add_argument("--format", choices=["json", "markdown"], default="markdown")
    evaluate.add_argument("--min-extraction-samples", type=int)
    evaluate.add_argument("--min-discovery-samples", type=int)
    evaluate.add_argument("--min-historical-samples", type=int)
    evaluate.add_argument("--min-briefing-samples", type=int)
    return parser


def run() -> None:
    args = _build_parser().parse_args()
    if args.command == "snapshot":
        data = asyncio.run(
            collect_snapshot(
                settings=Settings(),
                trial_start=_parse_time(args.trial_start),
                base_url=args.base_url,
            )
        )
        print(json.dumps(data, indent=2, default=str))
        return
    if args.command == "monitor":
        if args.duration_hours <= 0:
            raise SystemExit("--duration-hours must be > 0")
        if args.interval_seconds < 10:
            raise SystemExit("--interval-seconds must be >= 10")
        start = _parse_time(args.trial_start) if args.trial_start else datetime.now(UTC)
        asyncio.run(
            monitor(
                trial_start=start,
                duration_seconds=max(1, math.ceil(args.duration_hours * 3600)),
                interval_seconds=args.interval_seconds,
                base_url=args.base_url,
            )
        )
        return
    if args.command == "evaluate":
        samples = load_samples(args.input)
        overrides = {
            key: value
            for key, value in {
                "extraction": args.min_extraction_samples,
                "discovery": args.min_discovery_samples,
                "historical": args.min_historical_samples,
                "briefing": args.min_briefing_samples,
            }.items()
            if value is not None
        }
        report = evaluate_samples(samples, profile=args.profile, min_samples=overrides)
        if args.format == "json":
            print(json.dumps(report, indent=2, default=str))
        else:
            print(render_markdown(report))
        raise SystemExit(0 if report["state"] == "PASS" else 1)


if __name__ == "__main__":
    run()
