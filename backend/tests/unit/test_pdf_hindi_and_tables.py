"""Synthetic Hindi raster and vector-table regression tests for PDF extraction.

The scanned fixture contains only raster pixels, not embedded text or fonts.
These tests establish a minimum smoke baseline, not real-world OCR accuracy.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path
from zlib import decompress

import pytest

from newsintel.adapters.extractors.document_pdf import extract_pdf_document
from newsintel.domain.intelligence.pdf_table_layout import detect_table_candidates

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "hindi_scan_image_deflate.b64"


def _pdf(objects: list[bytes]) -> bytes:
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010} 00000 n \n".encode())
    content.extend((
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode())
    return bytes(content)


def _stream(data: bytes, *, prefix: bytes = b"") -> bytes:
    return (
        b"<< " + prefix + b" /Length " + str(len(data)).encode()
        + b" >>\nstream\n" + data + b"\nendstream"
    )


def _hindi_scan() -> bytes:
    packed = base64.b64decode(_FIXTURE.read_text().strip(), validate=True)
    assert len(decompress(packed)) == 1080 * 160 // 8
    drawing = b"q 540 0 0 80 0 0 cm /Im1 Do Q"
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 540 80] "
        b"/Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>",
        _stream(packed, prefix=(
            b"/Type /XObject /Subtype /Image /Width 1080 /Height 160 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /FlateDecode"
        )),
        _stream(drawing),
    ])


def _table_pdf() -> bytes:
    commands = []
    for y, cells in (
        (720, ("District", "Cases", "Reports")),
        (690, ("Bhopal", "21", "17")),
        (660, ("Indore", "15", "12")),
        (630, ("Ujjain", "11", "10")),
    ):
        for x, cell in zip((72, 310, 435), cells, strict=True):
            commands.append(f"BT /F1 12 Tf {x} {y} Td ({cell}) Tj ET")
    stream = "\n".join(commands).encode("ascii")
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        _stream(stream),
    ])


@pytest.mark.skipif(
    not all(shutil.which(x) for x in ("pdftotext", "pdftoppm", "pdfinfo", "tesseract")),
    reason="Poppler/Tesseract not installed",
)
def test_scanned_hindi_document_recovers_devanagari_but_marks_ocr_unverified() -> None:
    languages = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True, check=True,
    ).stdout.split()
    if "hin" not in languages:
        pytest.skip("Hindi language model is not installed")
    result = extract_pdf_document(
        _hindi_scan(),
        base_url="https://publisher.example/2026/10/30/hindi-scan.pdf",
        ocr_enabled=True, ocr_language="hin+eng",
    )
    assert "भारत" in result.text_content
    assert "सरकार" in result.text_content
    assert "योजना" in result.text_content
    assert result.metadata["ocr_page_count"] == 1
    assert result.metadata["document_requires_review"] is True
    assert "manual_ocr_review_recommended" in result.metadata["document_review_reasons"]
    assert result.metadata["document_pages"][0]["ocr_unverified"] is True
    assert "manual_ocr_review_recommended" in result.warnings
    assert result.metadata["document_table_candidates"] == []


@pytest.mark.skipif(
    not (shutil.which("pdftotext") and shutil.which("pdfinfo")),
    reason="Poppler not installed",
)
def test_vector_pdf_table_candidates_preserve_source_rows_but_are_unverified() -> None:
    report = extract_pdf_document(
        _table_pdf(), base_url="https://publisher.example/table-report.pdf",
    )
    table, = report.metadata["document_table_candidates"]
    assert table["page"] == 1
    assert table["source_url"].endswith("#page=1")
    assert table["header_cells"] == ["District", "Cases", "Reports"]
    assert [row["cells"] for row in table["rows"]][1:] == [
        ["Bhopal", "21", "17"],
        ["Indore", "15", "12"],
        ["Ujjain", "11", "10"],
    ]
    assert table["review_required"] is True
    assert table["verified_table"] is False
    assert report.metadata["document_table_review_required"] is True
    # Keep original source text intact; do not rewrite it from guessed cells.
    assert "Bhopal" in report.text_content


def test_paragraph_with_whitespace_does_not_produce_fake_table() -> None:
    layout = "This is  a paragraph with spacing\nIt has  two sections\n"
    assert detect_table_candidates(
        layout, page=1, source_url="https://example.org/report.pdf",
    ) == []
