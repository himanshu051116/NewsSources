"""Auditable offline metrics for manually labeled PDF extraction samples.

Do not infer a quality score from model confidence or synthetic tests. Metrics
are defined only relative to user-supplied, independently checked ground truth.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def edit_distance(reference: Sequence[Any], hypothesis: Sequence[Any]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, start=1):
        current = [i]
        for j, predicted in enumerate(hypothesis, start=1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (expected != predicted),
            ))
        previous = current
    return previous[-1]


def text_error_counts(reference: str, hypothesis: str) -> dict[str, int | float]:
    """CER counts Unicode codepoints; WER uses whitespace-delimited words.

    These are not grapheme-cluster error rates. Zero-length reference cases
    are invalid evaluation samples, not perfect scores.
    """
    ref = normalize_text(reference)
    pred = normalize_text(hypothesis)
    if not ref:
        raise ValueError("evaluation reference text cannot be empty")
    ref_words, pred_words = ref.split(), pred.split()
    return {
        "reference_characters": len(ref),
        "character_errors": edit_distance(ref, pred),
        "reference_words": len(ref_words),
        "word_errors": edit_distance(ref_words, pred_words),
    }


def table_cell_counts(
    reference_rows: list[list[str]],
    predicted_rows: list[list[str]],
) -> dict[str, int]:
    """Position-sensitive cell exactness; no semantic matching or invented cells."""
    if not reference_rows:
        raise ValueError("a gold table must have at least one labeled row")
    gold = {(r, c): normalize_text(value) for r, row in enumerate(reference_rows)
            for c, value in enumerate(row)}
    predicted = {(r, c): normalize_text(value) for r, row in enumerate(predicted_rows)
                 for c, value in enumerate(row)}
    correct = sum(predicted.get(pos) == value for pos, value in gold.items())
    return {
        "reference_cells": len(gold),
        "predicted_cells": len(predicted),
        "correct_cells": correct,
    }


def citation_counts(cases: list[dict[str, object]]) -> dict[str, int | float]:
    """Ground truth is a page ID, or None when the correct action is abstention."""
    if not cases:
        raise ValueError("citation evaluation requires labeled cases")
    correct = wrong = abstained = expected_anchors = correct_abstentions = missed = 0
    for case in cases:
        expected = case["expected_page"]
        predicted = case["predicted_page"]
        if expected is not None:
            if type(expected) is not int or expected < 1:
                raise ValueError("invalid gold citation page")
            expected_anchors += 1
        if predicted is not None and (type(predicted) is not int or predicted < 1):
            raise ValueError("invalid predicted citation page")
        if predicted is None:
            abstained += 1
            if expected is None:
                correct_abstentions += 1
            else:
                missed += 1
        elif predicted == expected:
            correct += 1
        else:
            wrong += 1
    proposed = correct + wrong
    return {
        "correct": correct,
        "wrong": wrong,
        "abstained": abstained,
        "expected_anchors": expected_anchors,
        "correct_abstentions": correct_abstentions,
        "missed_anchors": missed,
        "citation_precision": correct / proposed if proposed else 0.0,
        "citation_recall": correct / expected_anchors if expected_anchors else 0.0,
        "abstention_rate": abstained / len(cases),
    }


def aggregate_text_counts(rows: list[dict[str, int | float]]) -> dict[str, float | int]:
    if not rows:
        raise ValueError("no labeled text samples")
    chars = sum(int(row["reference_characters"]) for row in rows)
    words = sum(int(row["reference_words"]) for row in rows)
    char_errors = sum(int(row["character_errors"]) for row in rows)
    word_errors = sum(int(row["word_errors"]) for row in rows)
    return {
        "evaluated_pages": len(rows),
        "reference_characters": chars,
        "reference_words": words,
        "character_error_rate": char_errors / chars if chars else 0.0,
        "word_error_rate": word_errors / words if words else 0.0,
    }


def aggregate_table_counts(rows: list[dict[str, int]]) -> dict[str, float | int]:
    if not rows:
        raise ValueError("no labeled tables")
    gold = sum(row["reference_cells"] for row in rows)
    proposed = sum(row["predicted_cells"] for row in rows)
    correct = sum(row["correct_cells"] for row in rows)
    return {
        "evaluated_tables": len(rows),
        "reference_cells": gold,
        "predicted_cells": proposed,
        "cell_precision": correct / proposed if proposed else 0.0,
        "cell_recall": correct / gold if gold else 0.0,
    }
