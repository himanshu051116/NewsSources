"""PDF extraction contract: real Poppler, traceable offsets and conservative OCR."""
from __future__ import annotations

import shutil
from datetime import UTC, datetime

import pytest

from newsintel.adapters.extractors import document_pdf
from newsintel.domain.acquisition.article_filter import (
    UrlContentType,
    classify_article_url,
    should_admit_article_url,
)

FIRST = "Agency confirms water quality inspection results and issues a detailed report."
SECOND = "Officials say page two contains independent laboratory observations."


def sample_pdf(*, second: bool = True, blank_second: bool = False) -> bytes:
    """Build a tiny valid PDF without adding a runtime PDF-generation dependency."""
    def stream(text: str) -> bytes:
        command = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
        return (
            b"<< /Length " + str(len(command)).encode("ascii")
            + b" >>\nstream\n" + command + b"\nendstream"
        )

    pages = b"[3 0 R 6 0 R]" if second else b"[3 0 R]"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids " + pages + b" /Count " + (b"2" if second else b"1") + b" >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        stream(FIRST),
    ]
    if second:
        objs += [
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>",
            stream("" if blank_second else SECOND),
        ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objs, start=1):
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        body.extend(f"{offset:010} 00000 n \n".encode())
    body.extend((
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode())
    return bytes(body)


@pytest.mark.skipif(not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
                    reason="Poppler is unavailable on this runner")
def test_real_pdf_native_text_pages_have_exact_readable_offsets() -> None:
    pdf = sample_pdf()
    result = document_pdf.extract_pdf_document(
        pdf, base_url="https://publisher.example/reports/water-quality.pdf",
    )
    assert result.extraction_method == "pdf_native_pages"
    assert result.metadata["document_page_count"] == 2
    assert result.metadata["document_pages_processed"] == 2
    assert result.metadata["document_sha256"]
    pages = result.metadata["document_pages"]
    assert len(pages) == 2
    for index, expected in enumerate((FIRST, SECOND)):
        page = pages[index]
        span = result.text_content[page["char_start"]:page["char_end"]]
        assert span == expected
        assert page["page"] == index + 1
        assert page["source_url"].endswith(f"#page={index + 1}")
        assert page["extraction_method"] == "pdf_native_text"
        assert not page["ocr_unverified"]
    assert result.text_content == f"{FIRST}\n\n{SECOND}"


@pytest.mark.skipif(not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
                    reason="Poppler is unavailable on this runner")
def test_pdf_page_limit_is_disclosed_not_silently_omitted() -> None:
    result = document_pdf.extract_pdf_document(
        sample_pdf(), base_url="https://publisher.example/reports/water.pdf",
        max_pages=1,
    )
    assert result.metadata["document_truncated"]
    assert result.metadata["document_page_count"] == 2
    assert result.metadata["document_pages_processed"] == 1
    assert "pdf_page_limit_reached" in result.warnings
    assert result.text_content == FIRST


@pytest.mark.skipif(not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
                    reason="Poppler is unavailable on this runner")
def test_opt_in_ocr_is_labeled_unverified(monkeypatch) -> None:
    monkeypatch.setattr(
        document_pdf, "_ocr_page", lambda filename, page_number, **kwargs: "Scanned evidence",
    )
    result = document_pdf.extract_pdf_document(
        sample_pdf(second=False),
        base_url="https://publisher.example/scan.pdf",
        min_native_chars=999, ocr_enabled=True,
    )
    assert result.text_content == "Scanned evidence"
    assert result.metadata["ocr_page_count"] == 1
    assert result.metadata["document_pages"][0]["ocr_unverified"]
    assert "manual_ocr_review_recommended" in result.warnings


def test_pdf_signature_and_byte_cap_are_enforced_without_processing() -> None:
    with pytest.raises(document_pdf.PDFExtractionError, match="signature"):
        document_pdf.extract_pdf_document(
            b"<html>not a PDF</html>", base_url="https://publisher.example/bad.pdf",
        )
    with pytest.raises(document_pdf.PDFExtractionError, match="byte limit"):
        document_pdf.extract_pdf_document(
            b"%PDF-" + b"z" * 200, max_bytes=20,
            base_url="https://publisher.example/large.pdf",
        )


def test_pdf_url_classification_respects_recency_policy() -> None:
    url = "https://publisher.example/2026/10/30/reports/independent-report.pdf"
    assert classify_article_url(url).url_type is UrlContentType.DOCUMENT_REPORT
    accepted = should_admit_article_url(
        url, published_at=datetime(2026, 10, 30, tzinfo=UTC),
        observed_at=datetime(2026, 10, 31, tzinfo=UTC),
    )
    assert accepted.accepted
    rejected = should_admit_article_url(
        url, published_at=datetime(2026, 10, 30, tzinfo=UTC),
        observed_at=datetime(2026, 11, 20, tzinfo=UTC),
    )
    assert not rejected.accepted


@pytest.mark.skipif(
    not all(shutil.which(binary) for binary in ("pdftotext", "pdfinfo", "pdftoppm", "tesseract")),
    reason="Poppler/Tesseract are unavailable",
)
def test_real_tesseract_ocr_from_rendered_pdf_page() -> None:
    result = document_pdf.extract_pdf_document(
        sample_pdf(second=False),
        base_url="https://publisher.example/reports/scan.pdf",
        ocr_enabled=True, min_native_chars=999,
    )
    assert result.metadata["ocr_page_count"] == 1
    assert result.extraction_method == "pdf_pages_with_ocr"
    assert "Agency" in result.text_content
    assert result.metadata["document_pages"][0]["ocr_unverified"]


@pytest.mark.skipif(not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
                    reason="Poppler is unavailable")
def test_failed_ocr_does_not_discard_existing_native_text(monkeypatch) -> None:
    def broken_ocr(*args, **kwargs):
        raise document_pdf.PDFExtractionError("OCR package missing")

    monkeypatch.setattr(document_pdf, "_ocr_page", broken_ocr)
    result = document_pdf.extract_pdf_document(
        sample_pdf(second=False),
        base_url="https://publisher.example/native-plus-ocr.pdf",
        min_native_chars=999,
        ocr_enabled=True,
    )
    assert result.text_content == FIRST
    assert result.metadata["ocr_attempt_count"] == 1
    assert result.metadata["ocr_failure_count"] == 1
    assert result.metadata["document_pages"][0]["extraction_method"] == "pdf_native_text"
    assert "pdf_page_ocr_failed" in result.warnings


def test_pdf_subprocess_deadline_blocks_execution_before_start(monkeypatch) -> None:
    import time

    def forbidden(*args, **kwargs):
        pytest.fail("no conversion should start after budget exhaustion")

    monkeypatch.setattr(document_pdf.subprocess, "run", forbidden)
    with pytest.raises(document_pdf.PDFExtractionError, match="budget exhausted"):
        document_pdf._run(
            ["pdfinfo", "untrusted.pdf"], timeout=12,
            deadline=time.monotonic() - 0.5,
        )


@pytest.mark.skipif(
    not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
    reason="Poppler is unavailable",
)
def test_ocr_page_budget_preserves_native_text_and_warns(monkeypatch) -> None:
    calls = []

    def fake_ocr(filename, page_number, **kwargs):
        calls.append(page_number)
        return "Review needed on scanned material"

    monkeypatch.setattr(document_pdf, "_ocr_page", fake_ocr)
    result = document_pdf.extract_pdf_document(
        sample_pdf(), base_url="https://publisher.example/report.pdf",
        ocr_enabled=True, min_native_chars=999, max_ocr_pages=1,
    )
    assert calls == [1]
    assert result.metadata["ocr_attempt_count"] == 1
    assert result.metadata["ocr_page_budget"] == 1
    assert "pdf_ocr_page_budget_reached" in result.warnings
    assert SECOND in result.text_content
    assert result.metadata["document_pages"][1]["extraction_method"] == "pdf_native_text"


@pytest.mark.skipif(
    not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
    reason="Poppler is unavailable",
)
def test_pdf_total_text_character_limit_rejects_oversized_extraction() -> None:
    with pytest.raises(document_pdf.PDFExtractionError, match="character limit"):
        document_pdf.extract_pdf_document(
            sample_pdf(), base_url="https://publisher.example/report.pdf",
            max_text_characters=100,
        )


def test_pdf_budget_parameter_validation() -> None:
    for options in (
        {"max_ocr_pages": -1},
        {"max_duration_seconds": 2},
        {"max_text_characters": 50},
    ):
        with pytest.raises(ValueError):
            document_pdf.extract_pdf_document(
                b"%PDF-1.4", base_url="https://publisher.example/report.pdf",
                **options,
            )


@pytest.mark.skipif(
    not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
    reason="Poppler is unavailable",
)
def test_pdf_blank_page_forces_review_and_reduces_capture_score() -> None:
    result = document_pdf.extract_pdf_document(
        sample_pdf(blank_second=True),
        base_url="https://publisher.example/reports/incomplete.pdf",
    )
    assert result.metadata["document_page_count"] == 2
    assert result.metadata["document_pages_with_text"] == 1
    assert result.metadata["document_pages_without_text"] == 1
    assert result.metadata["document_text_page_ratio"] == 0.5
    assert result.metadata["document_requires_review"] is True
    assert "pdf_page_without_usable_text" in result.metadata["document_review_reasons"]
    assert result.metadata["extraction_quality_score"] <= 0.3
    assert result.text_content == FIRST


@pytest.mark.skipif(
    not shutil.which("pdftotext") or not shutil.which("pdfinfo"),
    reason="Poppler is unavailable",
)
def test_pdf_partial_page_limit_never_receives_full_capture_quality() -> None:
    result = document_pdf.extract_pdf_document(
        sample_pdf(),
        base_url="https://publisher.example/reports/partial.pdf",
        max_pages=1,
    )
    assert result.metadata["document_truncated"] is True
    assert result.metadata["document_requires_review"] is True
    assert "pdf_page_limit_reached" in result.metadata["document_review_reasons"]
    assert result.metadata["extraction_quality_score"] <= 0.3
