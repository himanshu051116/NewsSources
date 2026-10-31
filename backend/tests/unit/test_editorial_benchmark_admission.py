"""The offline gate must not confuse fictional or leaked cases with evidence."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))  # pytest pythonpath points at backend/src only

from qa.editorial_benchmark import prepare
SAMPLE = ROOT / "examples/synthetic_event_pair_manifest.json"


def _manifest() -> dict[str, object]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _run(tmp_path: Path, data: dict[str, object], *args: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "qa/editorial_benchmark.py"),
         "--manifest", str(path), *args],
        text=True, capture_output=True, timeout=30, check=False,
    )


def test_fictional_manifest_is_not_real_world_metrics() -> None:
    report, rows = prepare(SAMPLE)
    assert report["dataset_kind"] == "synthetic"
    assert report["eligible_for_real_world_metrics"] is False
    assert report["capture_hashes_verified"] == 4
    assert report["split_counts"] == {"train": 0, "dev": 1, "test": 1}
    assert {case["label"] for case in rows} == {"same", "different"}
    assert all(row["case_origin"] == "synthetic_test_only" for row in rows)


def test_synthetic_export_requires_explicit_flag(tmp_path: Path) -> None:
    output = tmp_path / "event_pairs.json"
    failed = _run(tmp_path, _manifest(), "--export", str(output))
    assert failed.returncode == 2
    assert "--allow-synthetic-export" in failed.stderr
    assert not output.exists()
    passed = _run(tmp_path, _manifest(), "--export", str(output),
                  "--allow-synthetic-export")
    assert passed.returncode == 0, passed.stderr
    assert len(json.loads(output.read_text(encoding="utf-8"))) == 2


def test_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    data = _manifest()
    data["cases"][0]["left"]["text"] += " Unsupported additional sentence."
    result = _run(tmp_path, data)
    assert result.returncode == 2
    assert "sha256" in result.stderr


def test_cross_split_lineage_and_capture_leakage_are_rejected(tmp_path: Path) -> None:
    data = _manifest()
    data["cases"][1]["left"]["source_lineage_key"] = data["cases"][0]["left"]["source_lineage_key"]
    assert "cross-split leakage" in _run(tmp_path, data).stderr
    data["cases"][1]["left"]["source_lineage_key"] = "other-origin"
    data["cases"][1]["left"]["text"] = data["cases"][0]["left"]["text"]
    data["cases"][1]["left"]["sha256"] = data["cases"][0]["left"]["sha256"]
    assert "cross-split leakage" in _run(tmp_path, data).stderr


def test_disagreement_requires_independent_adjudicator(tmp_path: Path) -> None:
    data = _manifest()
    case = data["cases"][0]
    case["reviews"][1]["label"] = "different"
    assert "adjudication" in _run(tmp_path, data).stderr
    case["adjudication"] = {"reviewer_id": "fictional-reviewer-1", "label": "same"}
    assert "independent" in _run(tmp_path, data).stderr
    case["adjudication"] = {"reviewer_id": "fictional-reviewer-3", "label": "same"}
    assert _run(tmp_path, data).returncode == 0
    case["reviews"][1]["reviewer_id"] = "FICTIONAL-reviewer-1"
    assert "different" in _run(tmp_path, data).stderr


def test_real_capture_requires_local_files_and_rights_metadata(tmp_path: Path) -> None:
    data = _manifest()
    data["dataset_kind"] = "real"
    data["rights_contact"] = "mock-rights-reviewer"
    assert "reserved example/local domain" in _run(tmp_path, data).stderr
    # This tests metadata validation with fictitious, ephemeral files. It does NOT
    # establish the existence, permission or factual truth of real news articles.
    for case in data["cases"]:
        for side in ("left", "right"):
            capture = case[side]
            name = f"{case['case_key']}-{side}.txt"
            (tmp_path / name).write_text(capture.pop("text"), encoding="utf-8")
            capture["text_path"] = name
            capture["rights_review"] = "approved_for_local_evaluation"
            capture["source_url"] = f"https://unit-test-newsroom.invalid.org/{name}"
    result = _run(tmp_path, data)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["publisher_rights_not_independently_verified"] is True
    data["cases"][0]["left"]["text_path"] = "../private.txt"
    assert "must be inside" in _run(tmp_path, data).stderr


def test_invalid_label_insecure_url_and_duplicate_key_rejected(tmp_path: Path) -> None:
    data = _manifest()
    data["cases"][0]["reviews"][0]["label"] = "supported"
    assert "reviewer label" in _run(tmp_path, data).stderr
    data = _manifest()
    data["cases"][0]["left"]["source_url"] = "http://localhost:8080/private"
    assert "HTTPS" in _run(tmp_path, data).stderr
    data = _manifest()
    data["cases"][0]["case_key"] = data["cases"][1]["case_key"]
    assert "duplicate case_key" in _run(tmp_path, data).stderr


def test_failed_manifest_does_not_write_report(tmp_path: Path) -> None:
    data = _manifest()
    data["cases"] = []
    output = tmp_path / "report.json"
    result = _run(tmp_path, data, "--report", str(output))
    assert result.returncode == 2
    assert not output.exists()

def test_export_only_held_out_split_without_skipping_full_audit(tmp_path: Path) -> None:
    output = tmp_path / "test-only.json"
    result = _run(tmp_path, _manifest(), "--allow-synthetic-export",
                  "--split", "test", "--export", str(output))
    assert result.returncode == 0, result.stderr
    rows = json.loads(output.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["evaluation_split"] == "test"
    assert json.loads(result.stdout)["export_case_count"] == 1
    assert json.loads(result.stdout)["case_count"] == 2


def test_malformed_field_types_fail_closed_without_tracebacks(tmp_path: Path) -> None:
    for field, value in (("dataset_kind", []), ("dataset_kind", {}),
                         ("dataset_kind", None)):
        data = _manifest()
        data[field] = value
        result = _run(tmp_path, data)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
    for part in ("split", "reviews"):
        data = _manifest()
        if part == "split":
            data["cases"][0]["split"] = []
        else:
            data["cases"][0]["reviews"][0]["label"] = []
        result = _run(tmp_path, data)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr

