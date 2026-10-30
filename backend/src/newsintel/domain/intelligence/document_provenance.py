"""Conservative, source-backed PDF page anchors for extracted claims.

A claim can be decomposed/rephrased; anchor its *original source sentence*, not
the generated clause. Never choose a page from similarity or ranking alone.
"""
from __future__ import annotations

import re
from hashlib import sha256
from typing import Any


def locate_pdf_source_sentence(
    document_text: str,
    page_records: object,
    source_sentence: str | None,
    *,
    expected_source_url: str | None = None,
) -> dict[str, Any] | None:
    """Locate one unambiguous sentence span within a single verified page.

    Return None when the sentence is absent, duplicated, malformed, split
    across pages, or its page span does not match the stored page SHA-256.
    A matching passage is provenance for extraction, not external verification.
    """
    if not isinstance(page_records, list) or not source_sentence:
        return None
    normalized = " ".join(source_sentence.split())
    if len(normalized) < 12 or len(normalized) > 2_000:
        return None
    # If a trusted origin is supplied, reject stale or poisoned metadata URLs.
    expected_base = expected_source_url.split("#", 1)[0] if expected_source_url else None
    # Admit layout whitespace differences, but no substitutions or paraphrases.
    expression = re.compile(re.escape(normalized).replace(r"\ ", r"\s+"))
    matches: list[dict[str, Any]] = []
    for record in page_records:
        if not isinstance(record, dict):
            return None
        start, end = record.get("char_start"), record.get("char_end")
        page = record.get("page")
        url = record.get("source_url")
        digest = record.get("text_sha256")
        if (
            type(start) is not int
            or type(end) is not int
            or type(page) is not int
            or start < 0
            or end <= start
            or end > len(document_text)
            or page < 1
            or not isinstance(url, str)
            or not url.endswith(f"#page={page}")
            or (expected_base is not None and url != f"{expected_base}#page={page}")
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            continue
        page_text = document_text[start:end]
        if sha256(page_text.encode("utf-8")).hexdigest() != digest:
            continue
        found = list(expression.finditer(page_text))
        for hit in found:
            matches.append(
                {
                    "page": page,
                    "page_url": url,
                    "char_start": start + hit.start(),
                    "char_end": start + hit.end(),
                    "page_text_sha256": digest,
                    "extraction_method": record.get("extraction_method"),
                    "ocr_unverified": record.get("ocr_unverified") is True,
                    "matching_basis": "single_page_source_sentence_exact_or_whitespace",
                    "independent_confirmation": False,
                }
            )
            if len(matches) > 1:
                return None
    return matches[0] if len(matches) == 1 else None
