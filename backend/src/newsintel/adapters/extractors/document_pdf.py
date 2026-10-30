"""Bounded, page-provenanced PDF text extraction with optional scanned-page OCR.

Uses Poppler (pdfinfo/pdftotext/pdftoppm) and the Tesseract CLI. Does not
accept local paths or perform network requests. Input bytes come from the
existing SSRF- and size-limited crawler fetcher.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit

from newsintel.adapters.extractors.article_html import ExtractedArticle


class PDFExtractionError(ValueError):
    """Unusable, unsafe, encrypted, or unsupported PDF document."""


def _run(command: list[str], *, timeout: int, max_output: int = 4_000_000) -> bytes:
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PDFExtractionError(f"PDF conversion unavailable or exceeded {timeout}s") from exc
    if result.returncode != 0:
        diagnostic = result.stderr.decode("utf-8", errors="replace")[:160]
        raise PDFExtractionError(f"PDF conversion failed: {diagnostic}")
    if len(result.stdout) > max_output:
        raise PDFExtractionError("PDF page output exceeds configured limit")
    return result.stdout


def _title(url: str, info: str) -> str:
    match = re.search(r"^Title:\s*(.+)$", info, flags=re.M)
    title = match.group(1).strip() if match else ""
    if not title:
        title = unquote(Path(urlsplit(url).path).stem).replace("-", " ").replace("_", " ")
    return " ".join(title.split())[:240] or "PDF document"


def _ocr_page(
    filename: Path, page_number: int, *,
    language: str, workdir: Path,
) -> str:
    image_base = workdir / f"page_{page_number}"
    _run(
        ["pdftoppm", "-f", str(page_number), "-l", str(page_number),
         "-r", "130", "-scale-to", "1800", "-singlefile", "-png",
         str(filename), str(image_base)],
        timeout=25,
    )
    image = image_base.with_suffix(".png")
    try:
        if not image.is_file() or image.stat().st_size > 10_000_000:
            raise PDFExtractionError("OCR page image exceeds size limit")
        text = _run(
            ["tesseract", str(image), "stdout", "-l", language, "--psm", "3"],
            timeout=30,
        )
        return text.decode("utf-8", errors="replace").strip()
    finally:
        image.unlink(missing_ok=True)


def extract_pdf_document(
    body: bytes,
    *,
    base_url: str,
    max_pages: int = 40,
    max_bytes: int = 8_000_000,
    ocr_enabled: bool = False,
    ocr_language: str = "eng",
    min_native_chars: int = 40,
) -> ExtractedArticle:
    """Return article-compatible text and exact per-page text offsets.

    OCR is unverified and explicitly labeled in metadata. The caller should
    retain these offsets when citing a passage; a string match alone is not
    sufficient page-level evidence.
    """
    if not body.startswith(b"%PDF-"):
        raise PDFExtractionError("PDF content signature missing")
    if len(body) > max_bytes:
        raise PDFExtractionError("PDF document exceeds configured byte limit")
    if not (1 <= max_pages <= 100):
        raise ValueError("max_pages must be 1..100")
    if not re.fullmatch(r"[a-z]{3}(?:\+[a-z]{3}){0,3}", ocr_language):
        raise ValueError("unsupported OCR language code")

    with TemporaryDirectory(prefix="newsintel-pdf-") as folder:
        root = Path(folder)
        filename = root / "source.pdf"
        filename.write_bytes(body)
        info = _run(["pdfinfo", str(filename)], timeout=12).decode(
            "utf-8", errors="replace",
        )
        match = re.search(r"^Pages:\s*(\d+)\s*$", info, flags=re.M)
        if not match or int(match.group(1)) < 1:
            raise PDFExtractionError("PDF page count unavailable")
        page_count = int(match.group(1))
        limit = min(page_count, max_pages)
        text_parts: list[str] = []
        pages: list[dict[str, object]] = []
        warnings: list[str] = []
        cursor = 0
        ocr_used = 0
        ocr_attempts = 0
        ocr_failures = 0

        if page_count > max_pages:
            warnings.append("pdf_page_limit_reached")
        for number in range(1, limit + 1):
            native = _run(
                ["pdftotext", "-f", str(number), "-l", str(number),
                 "-enc", "UTF-8", "-nopgbrk", str(filename), "-"],
                timeout=15,
            ).decode("utf-8", errors="replace").strip()
            text = native
            method = "pdf_native_text"
            if len(native.strip()) < min_native_chars and ocr_enabled:
                ocr_attempts += 1
                try:
                    ocr_text = _ocr_page(
                        filename, number, language=ocr_language, workdir=root,
                    )
                except PDFExtractionError:
                    ocr_failures += 1
                    warnings.append("pdf_page_ocr_failed")
                else:
                    if ocr_text:
                        text = ocr_text
                        method = "ocr_tesseract"
                        ocr_used += 1
                        warnings.append("ocr_text_unverified")
                    else:
                        warnings.append("pdf_page_ocr_returned_no_text")
            if not text:
                warnings.append("pdf_page_without_usable_text")
            if text and text_parts:
                cursor += 2
            start = cursor
            if text:
                text_parts.append(text)
                cursor += len(text)
            pages.append({
                "page": number,
                "source_url": f"{base_url}#page={number}",
                "char_start": start,
                "char_end": cursor,
                "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "extraction_method": method,
                "character_count": len(text),
                "ocr_unverified": method == "ocr_tesseract",
            })

    text_content = "\n\n".join(text_parts)
    if not text_content:
        warnings.append("missing_text_content")
    if ocr_used:
        warnings.append("manual_ocr_review_recommended")
    return ExtractedArticle(
        title=_title(base_url, info),
        byline=None,
        published_at=None,
        modified_at=None,
        language=None,
        canonical_url=base_url,
        text_content=text_content,
        content_sha256=sha256(text_content.encode("utf-8")).hexdigest(),
        extraction_method="pdf_pages_with_ocr" if ocr_used else "pdf_native_pages",
        metadata={
            "document_type": "application/pdf",
            "document_sha256": sha256(body).hexdigest(),
            "document_byte_size": len(body),
            "document_page_count": page_count,
            "document_pages_processed": limit,
            "document_pages": pages,
            "ocr_page_count": ocr_used,
            "ocr_attempt_count": ocr_attempts,
            "ocr_failure_count": ocr_failures,
            "document_truncated": limit < page_count,
            "extraction_quality_score": 0.5 if ocr_used else 0.8,
            "publication_date_basis": "unconfirmed",
            "word_count": len(text_content.split()),
        },
        warnings=tuple(dict.fromkeys(warnings)),
    )
