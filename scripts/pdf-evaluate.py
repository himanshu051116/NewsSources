#!/usr/bin/env python3
"""Offline labeled-PDF evaluation; no network, no publishing, no auto-truth labels.

Usage:
  uv run python scripts/pdf-evaluate.py --manifest /path/to/labeled.json --output report.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsintel.adapters.extractors.document_pdf import extract_pdf_document
from newsintel.domain.intelligence.document_provenance import locate_pdf_source_sentence
from newsintel.domain.intelligence.pdf_evaluation import (
    aggregate_table_counts,
    aggregate_text_counts,
    citation_counts,
    table_cell_counts,
    text_error_counts,
)


def evaluate_manifest(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    dataset_type = manifest.get("dataset_type")
    if dataset_type not in ("synthetic", "manually_labeled_real"):
        raise ValueError("dataset_type must explicitly be synthetic or manually_labeled_real")
    docs = manifest.get("documents")
    if not isinstance(docs, list) or not docs:
        raise ValueError("at least one labeled PDF is required")
    text_samples, table_samples, citations = [], [], []
    missing_table_candidates = 0
    false_table_candidates = 0
    unjudged_table_candidates = 0
    fully_labeled_table_documents = 0
    documents = []
    labeled_pages_total = 0
    original_pages_total = 0
    blank_pages_correct = 0
    hallucinated_blank_pages = 0
    for item in docs:
        if not isinstance(item, dict):
            raise ValueError("document entry must be an object")
        pdf_path = (manifest_path.parent / item["pdf_path"]).resolve()
        if pdf_path.suffix.lower() != ".pdf" or not pdf_path.is_file():
            raise ValueError(f"PDF not found: {pdf_path}")
        if pdf_path.stat().st_size > 8_000_000:
            raise ValueError("PDF exceeds 8 MB evaluation limit")
        result = extract_pdf_document(
            pdf_path.read_bytes(),
            base_url=item.get("source_url", "https://example.invalid/labeled.pdf"),
            ocr_enabled=bool(item.get("ocr_enabled", False)),
            ocr_language=item.get("ocr_language", "eng+hin"),
        )
        if result.metadata["document_truncated"]:
            raise ValueError(f"truncated document cannot be scored: {pdf_path.name}")
        pages = {page["page"]: page for page in result.metadata["document_pages"]}
        original_pages_total += result.metadata["document_page_count"]
        page_metrics = []
        labeled = set()
        for gold in item.get("pages", []):
            number, expected = gold["page"], gold["expected_text"]
            if number not in pages:
                raise ValueError(f"missing evaluated page {number} in {pdf_path.name}")
            if number in labeled:
                raise ValueError(f"duplicate labeled page {number} in {pdf_path.name}")
            labeled.add(number)
            record = pages[number]
            observed = result.text_content[record["char_start"]:record["char_end"]]
            if not expected.strip():
                # Blank-page truth has no CER denominator; detect OCR hallucination.
                hallucinated = bool(observed.strip())
                hallucinated_blank_pages += int(hallucinated)
                blank_pages_correct += int(not hallucinated)
                page_metrics.append({"page": number, "blank_page": True,
                                     "unexpected_text": hallucinated})
                continue
            score = text_error_counts(expected, observed)
            text_samples.append(score)
            page_metrics.append({"page": number, **score})
        labeled_pages_total += len(labeled)
        tables_by_page: dict[int, list[dict]] = {}
        for row in result.metadata["document_table_candidates"]:
            tables_by_page.setdefault(row["page"], []).append(row)
        for gold in item.get("tables", []):
            matches = tables_by_page.get(gold["page"], [])
            i = gold.get("candidate_index", 0)
            predicted = matches[i] if i < len(matches) else None
            if predicted is None:
                missing_table_candidates += 1
            prediction = [row["cells"] for row in predicted["rows"]] if predicted else []
            table_samples.append(table_cell_counts(gold["expected_rows"], prediction))
        expected_tables = item.get("tables", [])
        complete = item.get("tables_fully_annotated", False)
        if type(complete) is not bool:
            raise ValueError("tables_fully_annotated must be boolean")
        if complete:
            fully_labeled_table_documents += 1
        reviewed_candidates = {
            (case["page"], case.get("candidate_index", 0))
            for case in expected_tables
        }
        for page, candidates in tables_by_page.items():
            for index, _ in enumerate(candidates):
                if (page, index) in reviewed_candidates:
                    continue
                if complete:
                    false_table_candidates += 1
                else:
                    unjudged_table_candidates += 1
        for case in item.get("citations", []):
            match = locate_pdf_source_sentence(
                result.text_content,
                result.metadata["document_pages"],
                case["source_sentence"],
                expected_source_url=result.canonical_url,
            )
            citations.append({
                "expected_page": case["expected_page"],
                "predicted_page": match["page"] if match else None,
            })
        documents.append({
            "id": item["id"],
            "pages_total": result.metadata["document_page_count"],
            "pages_scored": len(page_metrics),
            "document_sha256": result.metadata["document_sha256"],
            "ocr_pages": result.metadata["ocr_page_count"],
            "warnings": list(result.warnings),
            "text_page_counts": page_metrics,
        })
    if not (labeled_pages_total or table_samples or citations):
        raise ValueError("no independently labeled text, table, or citation cases")
    return {
        "dataset_name": manifest.get("dataset_name", manifest_path.stem),
        "dataset_type": dataset_type,
        "not_a_real_world_benchmark": dataset_type == "synthetic",
        "documents_evaluated": len(documents),
        "labeling": {
            "labeled_pages": labeled_pages_total,
            "original_pages": original_pages_total,
            "labeled_page_coverage": labeled_pages_total / original_pages_total,
            "blank_pages_correct": blank_pages_correct,
            "hallucinated_blank_pages": hallucinated_blank_pages,
        },
        "text": aggregate_text_counts(text_samples) if text_samples else None,
        "tables": {
            **(aggregate_table_counts(table_samples) if table_samples else {}),
            "missing_table_candidates": missing_table_candidates,
            "false_table_candidates": (
                false_table_candidates
                if fully_labeled_table_documents == len(docs)
                else None
            ),
            "confirmed_false_candidates_in_fully_labeled_documents": false_table_candidates,
            "unjudged_table_candidates": unjudged_table_candidates,
            "fully_labeled_table_documents": fully_labeled_table_documents,
        },
        "citations": citation_counts(citations) if citations else None,
        "documents": documents,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Write machine-readable JSON report")
    parser.add_argument("--max-character-error-rate", type=float)
    parser.add_argument("--max-word-error-rate", type=float)
    parser.add_argument("--min-table-cell-recall", type=float)
    parser.add_argument("--min-citation-precision", type=float)
    parser.add_argument("--max-wrong-citations", type=int)
    parser.add_argument("--max-false-table-candidates", type=int)
    parser.add_argument("--min-labeled-page-coverage", type=float)
    parser.add_argument("--max-hallucinated-blank-pages", type=int)
    args = parser.parse_args()
    report = evaluate_manifest(args.manifest.resolve())
    checks: list[dict[str, object]] = []
    gates = (
        ("character_error_rate", "text", args.max_character_error_rate, "max"),
        ("word_error_rate", "text", args.max_word_error_rate, "max"),
        ("cell_recall", "tables", args.min_table_cell_recall, "min"),
        ("citation_precision", "citations", args.min_citation_precision, "min"),
        ("wrong", "citations", args.max_wrong_citations, "max"),
        ("false_table_candidates", "tables", args.max_false_table_candidates, "max"),
        ("labeled_page_coverage", "labeling", args.min_labeled_page_coverage, "min"),
        ("hallucinated_blank_pages", "labeling", args.max_hallucinated_blank_pages, "max"),
    )
    for key, group, threshold, direction in gates:
        if threshold is None:
            continue
        if threshold < 0 or (direction == "min" and threshold > 1):
            parser.error(f"invalid threshold for {key}")
        data = report.get(group)
        if not isinstance(data, dict) or key not in data or data[key] is None:
            parser.error(f"no complete ground-truth coverage for {group}.{key}")
        value = float(data[key])
        passed = value <= threshold if direction == "max" else value >= threshold
        checks.append({
            "metric": f"{group}.{key}",
            "observed": value, "threshold": threshold,
            "condition": direction, "passed": passed,
        })
    report["quality_gates"] = {
        "applied": bool(checks),
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["quality_gates"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
