"""Offline admission checks for independently reviewed event-link evaluation pairs.

A valid manifest proves internal consistency of supplied capture hashes and
review metadata, not publisher rights, factual truth, or sample representativeness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

MAX_MANIFEST_BYTES = 2_000_000
MAX_CASES = 500
MAX_CAPTURE_BYTES = 250_000
MAX_TEXT_CHARS = 35_000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_SPLITS = {"train", "dev", "test"}
ALLOWED_LABELS = {"same", "different"}


class ManifestError(ValueError):
    """A manifest has invalid or insufficient audit evidence."""


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ManifestError(f"{field}: expected nonempty string (up to 500 characters)")
    return value.strip()


def _timestamp(value: object, field: str) -> str:
    raw = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestError(f"{field}: invalid ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ManifestError(f"{field}: UTC offset required")
    return parsed.isoformat()


def _https_url(value: object, field: str, *, real: bool) -> str:
    raw = _required_text(value, field)
    try:
        parts = urlsplit(raw)
        invalid = (parts.scheme != "https" or not parts.hostname or parts.username
                   or parts.password or parts.port not in (None, 443))
    except ValueError as exc:
        raise ManifestError(f"{field}: HTTPS public source URL required") from exc
    if invalid:
        raise ManifestError(f"{field}: HTTPS public source URL required")
    host = parts.hostname.lower()
    if real and (host.endswith((".example", ".test", ".invalid", ".localhost",
                                    ".example.org", ".example.net", ".example.com"))
                 or host in {"localhost", "127.0.0.1", "::1", "example.com",
                             "example.org", "example.net"}):
        raise ManifestError(f"{field}: reserved example/local domain cannot be real source")
    return raw


def _capture_text(raw: dict[str, object], field: str, root: Path) -> str:
    inline = raw.get("text")
    relpath = raw.get("text_path")
    if (inline is None) == (relpath is None):
        raise ManifestError(f"{field}: supply exactly one of text or text_path")
    if inline is not None:
        if not isinstance(inline, str):
            raise ManifestError(f"{field}.text: must be text")
        text = inline
    else:
        if not isinstance(relpath, str) or not relpath or len(relpath) > 240:
            raise ManifestError(f"{field}.text_path: invalid relative file path")
        requested = Path(relpath)
        if requested.is_absolute() or ".." in requested.parts:
            raise ManifestError(f"{field}.text_path: must be inside manifest folder")
        path = (root / requested).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            raise ManifestError(f"{field}.text_path: file missing or escapes manifest folder")
        if path.stat().st_size > MAX_CAPTURE_BYTES:
            raise ManifestError(f"{field}.text_path: capture too large")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ManifestError(f"{field}.text_path: cannot read UTF-8 file") from exc
    if not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise ManifestError(f"{field}: capture must contain 1..{MAX_TEXT_CHARS} text characters")
    return text


def _capture(raw: object, field: str, root: Path, *, real: bool) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ManifestError(f"{field}: capture must be object")
    title = _required_text(raw.get("title"), f"{field}.title")
    url = _https_url(raw.get("source_url"), f"{field}.source_url", real=real)
    captured = _timestamp(raw.get("captured_at"), f"{field}.captured_at")
    lineage = _required_text(raw.get("source_lineage_key"), f"{field}.source_lineage_key")
    expected = raw.get("sha256")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        raise ManifestError(f"{field}.sha256: lowercase SHA-256 required")
    if real and raw.get("rights_review") != "approved_for_local_evaluation":
        raise ManifestError(f"{field}.rights_review: explicit evaluation approval required")
    if real and "text" in raw:
        raise ManifestError(f"{field}: real captures must use local text_path, not inlined content")
    text = _capture_text(raw, field, root)
    actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if actual != expected:
        raise ManifestError(f"{field}.sha256: local capture differs from registered hash")
    return {"title": title, "source_url": url, "captured_at": captured,
            "source_lineage_key": lineage, "sha256": expected, "text": text}


def _final_label(raw: object, field: str) -> str:
    if not isinstance(raw, dict) or not isinstance(raw.get("reviews"), list):
        raise ManifestError(f"{field}.reviews: two independent reviewer entries required")
    reviews = raw["reviews"]
    if len(reviews) != 2:
        raise ManifestError(f"{field}.reviews: exactly two independent reviews required")
    ids: set[str] = set()
    labels: list[str] = []
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            raise ManifestError(f"{field}.reviews[{index}]: expected object")
        reviewer = _required_text(review.get("reviewer_id"), f"{field}.reviewer_id").casefold()
        if reviewer in ids:
            raise ManifestError(f"{field}: reviewers must be different")
        ids.add(reviewer)
        label = review.get("label")
        if not isinstance(label, str) or label not in ALLOWED_LABELS:
            raise ManifestError(f"{field}: reviewer label must be 'same' or 'different'")
        labels.append(label)
    adjudication = raw.get("adjudication")
    if labels[0] == labels[1]:
        if adjudication is not None:
            raise ManifestError(f"{field}: adjudication not expected for matching reviews")
        return labels[0]
    if not isinstance(adjudication, dict):
        raise ManifestError(f"{field}: disagreeing reviewers require third-party adjudication")
    adjudicator = _required_text(adjudication.get("reviewer_id"), f"{field}.adjudicator").casefold()
    if adjudicator in ids:
        raise ManifestError(f"{field}: adjudicator must be independent")
    result = adjudication.get("label")
    if not isinstance(result, str) or result not in ALLOWED_LABELS:
        raise ManifestError(f"{field}.adjudication: missing final event label")
    return result


def prepare(manifest: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    path = manifest.resolve()
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest too large")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ManifestError("manifest must be UTF-8 JSON") from exc
    if not isinstance(doc, dict):
        raise ManifestError("manifest must be a JSON object")
    kind = doc.get("dataset_kind")
    if not isinstance(kind, str) or kind not in {"real", "synthetic"}:
        raise ManifestError("dataset_kind must be 'real' or 'synthetic'")
    real = kind == "real"
    dataset = _required_text(doc.get("dataset_id"), "dataset_id")
    if real:
        if doc.get("protocol_version") != "event-pair-review-v1":
            raise ManifestError("real dataset requires event-pair-review-v1 annotation protocol")
        if doc.get("rights_contact") is None:
            raise ManifestError("real dataset requires a rights_contact identifier")
        _required_text(doc.get("rights_contact"), "rights_contact")
    cases = doc.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > MAX_CASES:
        raise ManifestError(f"cases must contain 1..{MAX_CASES} cases")
    seen_ids: set[str] = set()
    grouped: dict[str, set[str]] = defaultdict(set)
    export: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    for index, raw in enumerate(cases):
        where = f"cases[{index}]"
        if not isinstance(raw, dict):
            raise ManifestError(f"{where}: expected object")
        case_key = _required_text(raw.get("case_key"), f"{where}.case_key")
        if case_key in seen_ids:
            raise ManifestError(f"{where}: duplicate case_key {case_key}")
        seen_ids.add(case_key)
        split = raw.get("split")
        if not isinstance(split, str) or split not in ALLOWED_SPLITS:
            raise ManifestError(f"{where}.split: use train, dev or test")
        group = _required_text(raw.get("event_group_key"), f"{where}.event_group_key")
        left = _capture(raw.get("left"), f"{where}.left", path.parent, real=real)
        right = _capture(raw.get("right"), f"{where}.right", path.parent, real=real)
        label = _final_label(raw, where)
        if left["sha256"] == right["sha256"] and label == "different":
            raise ManifestError(f"{where}: identical captured text cannot be different events")
        for key in (f"event:{group}", f"capture:{left['sha256']}",
                    f"capture:{right['sha256']}",
                    f"lineage:{left['source_lineage_key']}",
                    f"lineage:{right['source_lineage_key']}"):
            grouped[key].add(split)
        counts[split] += 1
        counts[f"label_{label}"] += 1
        export.append({"case_key": case_key, "label": label, "language":
                       _required_text(raw.get("language"), f"{where}.language"),
                       "category": _required_text(raw.get("category"), f"{where}.category"),
                       "left_title": left["title"], "left_text": left["text"],
                       "right_title": right["title"], "right_text": right["text"],
                       "left_published_at": left["captured_at"],
                       "right_observed_at": right["captured_at"],
                       "case_origin": "independently_reviewed_capture" if real else "synthetic_test_only",
                       "evaluation_split": split,
                       "evaluation_dataset_id": dataset})
    leaks = sorted(key for key, splits in grouped.items() if len(splits) > 1)
    if leaks:
        raise ManifestError("cross-split leakage detected: " + ", ".join(leaks[:8]))
    report: dict[str, object] = {
        "dataset_id": dataset,
        "dataset_kind": kind,
        "case_count": len(export),
        "split_counts": {k: counts[k] for k in ("train", "dev", "test")},
        "label_counts": {k: counts[f"label_{k}"] for k in ("same", "different")},
        "provenance_validation": "passed",
        "capture_hashes_verified": len(export) * 2,
        "independent_double_review_checked": True,
        "cross_split_leakage_checked": True,
        "eligible_for_real_world_metrics": real,
        "representativeness_not_assessed": True,
        "publisher_rights_not_independently_verified": True,
    }
    return report, export


def _preflight_output(path: Path, *, manifest: Path, real_export: bool) -> None:
    """Refuse to overwrite an input or publish full real-source captures."""
    resolved = path.resolve()
    if resolved == manifest.resolve():
        raise ManifestError("output path must not be the input manifest")
    if path.exists() or path.is_symlink():
        raise ManifestError(f"output already exists (will not overwrite): {path}")
    if real_export:
        repo = Path(__file__).resolve().parents[1]
        safe = repo / "evaluation" / "results"
        if resolved.is_relative_to(repo) and not resolved.is_relative_to(safe):
            raise ManifestError("real capture exports inside the repo require evaluation/results/")


def _write_new_outputs(outputs: list[tuple[Path, str]]) -> None:
    """Create output files exclusively; roll back on a write failure."""
    created: list[Path] = []
    try:
        for path, content in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                created.append(path)
                stream.write(content)
    except OSError:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        raise


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="write metadata-only report JSON")
    parser.add_argument("--export", type=Path, help="write event benchmark input with capture texts")
    parser.add_argument("--allow-synthetic-export", action="store_true",
                        help="allow explicitly synthetic smoke-test export (never real-world evidence)")
    parser.add_argument("--split", choices=("train", "dev", "test"),
                        help="export only this split while auditing all cases")
    args = parser.parse_args()
    try:
        report, payload = prepare(args.manifest)
        if args.export is not None and report["dataset_kind"] == "synthetic" and not args.allow_synthetic_export:
            raise ManifestError("synthetic export requires --allow-synthetic-export")
        if args.split and not args.export:
            raise ManifestError("--split requires --export")
        selected = [case for case in payload if case["evaluation_split"] == args.split] if args.split else payload
        if args.export is not None:
            if not selected:
                raise ManifestError("requested split contains no cases")
            report["export_split"] = args.split or "all"
            report["export_case_count"] = len(selected)
        report["manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
        report["validation_scope"] = "local_hash_and_metadata_checks_only"
        report["real_world_accuracy_certified"] = False
        outputs: list[tuple[Path, str]] = []
        if args.export is not None:
            exported = json.dumps(selected, indent=2, ensure_ascii=False) + "\n"
            report["export_sha256"] = hashlib.sha256(exported.encode("utf-8")).hexdigest()
            outputs.append((args.export, exported))
        if args.report is not None:
            outputs.append((args.report, json.dumps(report, indent=2) + "\n"))
        if args.report is not None and args.export is not None and (
            args.report.resolve() == args.export.resolve()
        ):
            raise ManifestError("--report and --export must use different files")
        for path, _content in outputs:
            _preflight_output(path, manifest=args.manifest,
                              real_export=path == args.export and report["dataset_kind"] == "real")
        _write_new_outputs(outputs)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except (ManifestError, OSError) as exc:
        print(f"Benchmark admission rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
