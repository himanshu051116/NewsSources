"""Auditable PDF evaluation metrics and an actual offline CLI round trip."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from newsintel.domain.intelligence.pdf_evaluation import (
    aggregate_table_counts,
    aggregate_text_counts,
    citation_counts,
    table_cell_counts,
    text_error_counts,
)


def _one_page_pdf(text: str) -> bytes:
    cmd = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    stream = (
        b"<< /Length " + str(len(cmd)).encode()
        + b" >>\nstream\n" + cmd + b"\nendstream"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        stream,
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{n} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(data)


def test_unicode_metrics_have_valid_error_denominators() -> None:
    exact = text_error_counts("भारत सरकार", "भारत सरकार")
    partial = text_error_counts("भारत सरकार", "भारत")
    assert exact["character_errors"] == 0
    assert exact["word_errors"] == 0
    assert partial["word_errors"] == 1
    aggregate = aggregate_text_counts([exact, partial])
    assert aggregate["evaluated_pages"] == 2
    assert 0 < aggregate["character_error_rate"] < 1
    assert aggregate["word_error_rate"] == 0.25
    with pytest.raises(ValueError):
        text_error_counts("  ", "hallucination")


def test_table_cell_metrics_penalize_wrong_number_and_missing_row() -> None:
    gold = [["District", "Count", "Total"], ["Delhi", "31", "11"],
            ["Bhopal", "27", "7"]]
    predicted = [["District", "Count", "Total"], ["Delhi", "13", "11"]]
    one = table_cell_counts(gold, predicted)
    assert one == {"reference_cells": 9, "predicted_cells": 6, "correct_cells": 5}
    report = aggregate_table_counts([one])
    assert report["cell_precision"] == 5 / 6
    assert report["cell_recall"] == 5 / 9


def test_citation_metrics_distinguish_false_anchor_and_correct_abstention() -> None:
    result = citation_counts([
        {"expected_page": 2, "predicted_page": 2},
        {"expected_page": 3, "predicted_page": 1},
        {"expected_page": 4, "predicted_page": None},
        {"expected_page": None, "predicted_page": None},
    ])
    assert result["correct"] == 1
    assert result["wrong"] == 1
    assert result["missed_anchors"] == 1
    assert result["correct_abstentions"] == 1
    assert result["citation_precision"] == 0.5
    assert result["citation_recall"] == 1 / 3


@pytest.mark.skipif(not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
                    reason="Poppler conversion tools absent")
def test_cli_scores_labeled_local_pdf_and_never_promotes_synthetic_to_real(tmp_path) -> None:
    text = "Officials reported 31 incidents during June 2026."
    filename = tmp_path / "report.pdf"
    filename.write_bytes(_one_page_pdf(text))
    manifest = tmp_path / "gold.json"
    manifest.write_text(json.dumps({
        "dataset_name": "single-page smoke case",
        "dataset_type": "synthetic",
        "documents": [{
            "id": "sample",
            "pdf_path": "report.pdf",
            "source_url": "https://publisher.example/report.pdf",
            "pages": [{"page": 1, "expected_text": text}],
            "citations": [
                {"source_sentence": text, "expected_page": 1},
                {"source_sentence": "Unmentioned claim", "expected_page": None},
            ],
        }],
    }), encoding="utf-8")
    script = Path(__file__).resolve().parents[3] / "scripts" / "pdf-evaluate.py"
    output = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(script), "--manifest", str(manifest),
         "--output", str(output)],
        capture_output=True, text=True, check=True, timeout=90,
    )
    assert proc.returncode == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["not_a_real_world_benchmark"] is True
    assert result["text"]["character_error_rate"] == 0
    assert result["text"]["word_error_rate"] == 0
    assert result["citations"]["citation_precision"] == 1
    assert result["citations"]["correct_abstentions"] == 1
    assert result["documents_evaluated"] == 1
    assert result["tables"]["false_table_candidates"] is None
    assert result["tables"]["fully_labeled_table_documents"] == 0
    passing = subprocess.run(
        [sys.executable, str(script), "--manifest", str(manifest),
         "--max-character-error-rate", "0", "--min-citation-precision", "1",
         "--max-wrong-citations", "0"],
        capture_output=True, text=True, timeout=90, check=True,
    )
    assert json.loads(passing.stdout)["quality_gates"]["passed"] is True
    bad_reference = json.loads(manifest.read_text(encoding="utf-8"))
    bad_reference["documents"][0]["pages"][0]["expected_text"] += " Extra"
    manifest.write_text(json.dumps(bad_reference), encoding="utf-8")
    failing = subprocess.run(
        [sys.executable, str(script), "--manifest", str(manifest),
         "--max-character-error-rate", "0"],
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert failing.returncode == 1
    assert json.loads(failing.stdout)["quality_gates"]["passed"] is False


@pytest.mark.skipif(not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
                    reason="Poppler conversion tools absent")
def test_table_false_positive_gate_requires_complete_ground_truth(tmp_path) -> None:
    pdf = tmp_path / "one.pdf"
    pdf.write_bytes(_one_page_pdf("A report without any detected table."))
    manifest = tmp_path / "gold.json"
    entry = {
        "dataset_type": "synthetic",
        "documents": [{
            "id": "no-table", "pdf_path": pdf.name, "pages": [{
                "page": 1, "expected_text": "A report without any detected table.",
            }],
        }],
    }
    manifest.write_text(json.dumps(entry), encoding="utf-8")
    script = Path(__file__).resolve().parents[3] / "scripts" / "pdf-evaluate.py"
    rejected = subprocess.run(
        [sys.executable, str(script), "--manifest", str(manifest),
         "--max-false-table-candidates", "0"],
        capture_output=True, text=True, check=False, timeout=90,
    )
    assert rejected.returncode != 0
    assert "no complete ground-truth coverage" in rejected.stderr
    entry["documents"][0]["tables_fully_annotated"] = True
    manifest.write_text(json.dumps(entry), encoding="utf-8")
    accepted = subprocess.run(
        [sys.executable, str(script), "--manifest", str(manifest),
         "--max-false-table-candidates", "0"],
        capture_output=True, text=True, check=True, timeout=90,
    )
    report = json.loads(accepted.stdout)
    assert report["tables"]["false_table_candidates"] == 0
    assert report["tables"]["fully_labeled_table_documents"] == 1
