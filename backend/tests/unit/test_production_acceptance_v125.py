from newsintel.acceptance import evaluate_samples, render_markdown


def _snapshot(*, elapsed: float, ready: bool = True, processed: int = 30, failed: int = 1):
    return {
        "schema": "newsintel-acceptance-snapshot-v1",
        "trial_start": "2026-10-14T00:00:00Z",
        "captured_at": "2026-10-15T00:00:00Z" if elapsed >= 86400 else "2026-10-14T00:10:00Z",
        "elapsed_seconds": elapsed,
        "api_live": True,
        "api_ready": ready,
        "articles_observed": processed,
        "extraction": {
            "processed": processed,
            "failed": failed,
            "rejected": 2,
            "pending": 0,
            "eligible_terminal": processed + failed,
            "success_rate": processed / (processed + failed),
        },
        "discovery": {"timestamped_samples": 20, "p95_seconds": 90.0},
        "historical": {
            "eligible_versions": 20,
            "completed_within_10m": 20,
            "completion_rate_within_10m": 1.0,
        },
        "briefings": {
            "eligible_versions": 10,
            "covered_within_12m": 10,
            "completion_rate_within_12m": 1.0,
        },
        "leases": {
            "stale_poll_max_seconds": 0.0,
            "stale_article_max_seconds": 0.0,
            "poll_lease_seconds": 120,
            "article_lease_seconds": 120,
        },
        "publishers": [],
    }


def test_acceptance_passes_only_when_duration_volume_and_slos_pass():
    samples = [_snapshot(elapsed=0), _snapshot(elapsed=86400)]
    report = evaluate_samples(samples, profile="24h")
    assert report["state"] == "PASS"
    assert all(item["state"] == "PASS" for item in report["checks"])
    assert "Production Acceptance Report" in render_markdown(report)


def test_acceptance_blocks_on_insufficient_trial_volume():
    sample = _snapshot(elapsed=86400, processed=2, failed=0)
    sample["discovery"]["timestamped_samples"] = 2
    sample["historical"]["eligible_versions"] = 2
    sample["briefings"]["eligible_versions"] = 1
    report = evaluate_samples([sample], profile="24h")
    assert report["state"] == "BLOCKED"
    blocked = {item["name"] for item in report["checks"] if item["state"] == "BLOCKED"}
    assert "terminal_extraction_success" in blocked
    assert "publication_to_discovery_p95" in blocked


def test_acceptance_fails_on_readiness_or_persistent_stale_leases():
    samples = [_snapshot(elapsed=0, ready=False), _snapshot(elapsed=86400, ready=True)]
    samples[-1]["leases"]["stale_article_max_seconds"] = 400.0
    report = evaluate_samples(samples, profile="24h")
    assert report["state"] == "FAIL"
    failed = {item["name"] for item in report["checks"] if item["state"] == "FAIL"}
    assert "api_readiness" in failed
    assert "persistent_stale_worker_leases" in failed


def test_acceptance_counts_monitor_errors_against_readiness_availability():
    good = _snapshot(elapsed=86400, ready=True)
    error = {
        "schema": "newsintel-acceptance-snapshot-error-v1",
        "trial_start": "2026-10-14T00:00:00Z",
        "captured_at": "2026-10-14T12:00:00Z",
        "elapsed_seconds": 43200,
        "api_live": False,
        "api_ready": False,
        "error_type": "DatabaseError",
    }
    report = evaluate_samples([_snapshot(elapsed=0), error, good], profile="24h")
    assert report["state"] == "FAIL"
    assert report["sample_count"] == 3
    assert report["error_snapshot_count"] == 1
    readiness = next(item for item in report["checks"] if item["name"] == "api_readiness")
    assert readiness["state"] == "FAIL"
