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
    documents = []
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
        page_metrics = []
        for gold in item.get("pages", []):
            number, expected = gold["page"], gold["expected_text"]
            if number not in pages:
                raise ValueError(f"missing evaluated page {number} in {pdf_path.name}")
            record = pages[number]
            observed = result.text_content[record["char_start"]:record["char_end"]]
            score = text_error_counts(expected, observed)
            text_samples.append(score)
            page_metrics.append({"page": number, **score})
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
        target_pages = {case["page"] for case in expected_tables}
        false_table_candidates += sum(
            len(candidates) for page, candidates in tables_by_page.items()
            if page not in target_pages
        )
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
            "ocr_pages": result.metadata["ocr_page_count"],
            "warnings": list(result.warnings),
            "text_page_counts": page_metrics,
        })
    if not (text_samples or table_samples or citations):
        raise ValueError("no independently labeled text, table, or citation cases")
    return {
        "dataset_name": manifest.get("dataset_name", manifest_path.stem),
        "dataset_type": dataset_type,
        "not_a_real_world_benchmark": dataset_type == "synthetic",
        "documents_evaluated": len(documents),
        "text": aggregate_text_counts(text_samples) if text_samples else None,
        "tables": {
            **(aggregate_table_counts(table_samples) if table_samples else {}),
            "missing_table_candidates": missing_table_candidates,
            "false_table_candidates_on_unlabeled_pages": false_table_candidates,
        },
        "citations": citation_counts(citations) if citations else None,
        "documents": documents,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Write machine-readable JSON report")
    args = parser.parse_args()
    report = evaluate_manifest(args.manifest.resolve())
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
