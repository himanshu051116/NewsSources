"""Conservative layout-based PDF table *candidates*, never verified facts.

Preserve text rows and cells exactly as emitted by Poppler -layout. Multi-column
prose, malformed layouts and OCR can produce false tables; label every result
as needing manual review, and never use these rows for claim verification.
"""
from __future__ import annotations

import re


def detect_table_candidates(
    layout_text: str, *, page: int, source_url: str,
    max_rows: int = 35, max_columns: int = 8,
) -> list[dict[str, object]]:
    if not isinstance(layout_text, str) or not layout_text:
        return []
    detected: list[dict[str, object]] = []
    block: list[dict[str, object]] = []

    def finish() -> None:
        if len(block) < 3:
            block.clear()
            return
        counts = {len(row["cells"]) for row in block}
        if len(counts) != 1 or not (3 <= next(iter(counts)) <= max_columns):
            block.clear()
            return
        numeric_rows = sum(
            any(re.search(r"\d", str(cell)) for cell in row["cells"][1:])
            for row in block[1:]
        )
        if numeric_rows < 2:
            block.clear()
            return
        detected.append({
            "page": page,
            "source_url": f"{source_url.split('#', 1)[0]}#page={page}",
            "layout_method": "pdftotext_layout_whitespace_heuristic",
            "review_required": True,
            "verified_table": False,
            "header_cells": block[0]["cells"],
            "rows": list(block[:max_rows]),
            "truncated": len(block) > max_rows,
        })
        block.clear()

    blank_run = 0
    for index, line in enumerate(layout_text.splitlines(), 1):
        if not line.strip():
            blank_run += 1
            if blank_run > 1:
                finish()
            continue
        blank_run = 0
        parts = [s.strip() for s in re.split(r" {2,}", line.strip()) if s.strip()]
        if not (3 <= len(parts) <= max_columns):
            finish()
            continue
        if block and len(parts) != len(block[0]["cells"]):
            finish()
        block.append({"source_line_number": index, "raw_text": line, "cells": parts})
    finish()
    return detected[:4]
