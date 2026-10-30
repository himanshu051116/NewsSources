from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from newsintel.domain.intelligence.claims import (
    extract_quantities,
    extract_temporal_references,
    split_sentences,
)

VERSION_DIFF_METHODOLOGY = "article-version-diff-v1"


class VersionChangeKind(StrEnum):
    TITLE_CHANGED = "title_changed"
    SENTENCE_ADDED = "sentence_added"
    SENTENCE_REMOVED = "sentence_removed"
    SENTENCE_REPLACED = "sentence_replaced"
    NUMERIC_CHANGED = "numeric_changed"
    TEMPORAL_CHANGED = "temporal_changed"
    CORRECTION_NOTICE = "correction_notice"


class ChangeSignificance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class VersionChange:
    kind: VersionChangeKind
    significance: ChangeSignificance
    old_text: str | None
    new_text: str | None
    old_sentence_index: int | None = None
    new_sentence_index: int | None = None
    similarity: float | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class VersionDiff:
    methodology_version: str
    changes: tuple[VersionChange, ...]
    added_count: int
    removed_count: int
    replaced_count: int
    numeric_change_count: int
    temporal_change_count: int
    material_change_count: int


def diff_article_versions(
    *,
    old_title: str,
    old_text: str,
    new_title: str,
    new_text: str,
    max_changes: int = 100,
) -> VersionDiff:
    changes: list[VersionChange] = []
    if _norm(old_title) != _norm(new_title):
        similarity = SequenceMatcher(None, _norm(old_title), _norm(new_title)).ratio()
        changes.append(
            VersionChange(
                kind=VersionChangeKind.TITLE_CHANGED,
                significance=(
                    ChangeSignificance.HIGH if similarity < 0.65 else ChangeSignificance.MEDIUM
                ),
                old_text=old_title,
                new_text=new_title,
                similarity=round(similarity, 4),
            )
        )

    old_sentences = split_sentences(old_text)
    new_sentences = split_sentences(new_text)
    matcher = SequenceMatcher(
        None,
        tuple(_norm(item) for item in old_sentences),
        tuple(_norm(item) for item in new_sentences),
        autojunk=False,
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for offset, sentence in enumerate(old_sentences[i1:i2]):
                changes.append(
                    VersionChange(
                        kind=VersionChangeKind.SENTENCE_REMOVED,
                        significance=ChangeSignificance.MEDIUM,
                        old_text=sentence,
                        new_text=None,
                        old_sentence_index=i1 + offset,
                    )
                )
        elif tag == "insert":
            for offset, sentence in enumerate(new_sentences[j1:j2]):
                changes.append(
                    _added_change(sentence, new_sentence_index=j1 + offset)
                )
        elif tag == "replace":
            changes.extend(
                _replacement_changes(
                    old_sentences[i1:i2],
                    new_sentences[j1:j2],
                    old_start=i1,
                    new_start=j1,
                )
            )
        if len(changes) >= max_changes:
            break

    changes = changes[:max_changes]
    return _summarize(tuple(changes))


def _replacement_changes(
    old_items: tuple[str, ...],
    new_items: tuple[str, ...],
    *,
    old_start: int,
    new_start: int,
) -> list[VersionChange]:
    changes: list[VersionChange] = []
    paired = min(len(old_items), len(new_items))
    for offset in range(paired):
        old = old_items[offset]
        new = new_items[offset]
        similarity = SequenceMatcher(None, _norm(old), _norm(new)).ratio()
        old_quantities = extract_quantities(old)
        new_quantities = extract_quantities(new)
        old_temporal = extract_temporal_references(old)
        new_temporal = extract_temporal_references(new)
        quantity_changed = _normalized_quantities(old_quantities) != _normalized_quantities(
            new_quantities
        )
        temporal_changed = _normalized_temporal(old_temporal) != _normalized_temporal(new_temporal)

        if similarity >= 0.35 and quantity_changed and (old_quantities or new_quantities):
            changes.append(
                VersionChange(
                    kind=VersionChangeKind.NUMERIC_CHANGED,
                    significance=ChangeSignificance.HIGH,
                    old_text=old,
                    new_text=new,
                    old_sentence_index=old_start + offset,
                    new_sentence_index=new_start + offset,
                    similarity=round(similarity, 4),
                    metadata={
                        "old_quantities": list(old_quantities),
                        "new_quantities": list(new_quantities),
                    },
                )
            )
        elif similarity >= 0.35 and temporal_changed and (old_temporal or new_temporal):
            changes.append(
                VersionChange(
                    kind=VersionChangeKind.TEMPORAL_CHANGED,
                    significance=ChangeSignificance.HIGH,
                    old_text=old,
                    new_text=new,
                    old_sentence_index=old_start + offset,
                    new_sentence_index=new_start + offset,
                    similarity=round(similarity, 4),
                    metadata={
                        "old_temporal_references": list(old_temporal),
                        "new_temporal_references": list(new_temporal),
                    },
                )
            )
        else:
            changes.append(
                VersionChange(
                    kind=VersionChangeKind.SENTENCE_REPLACED,
                    significance=(
                        ChangeSignificance.HIGH
                        if similarity < 0.35
                        else ChangeSignificance.MEDIUM
                    ),
                    old_text=old,
                    new_text=new,
                    old_sentence_index=old_start + offset,
                    new_sentence_index=new_start + offset,
                    similarity=round(similarity, 4),
                )
            )
    for offset, old in enumerate(old_items[paired:]):
        changes.append(
            VersionChange(
                kind=VersionChangeKind.SENTENCE_REMOVED,
                significance=ChangeSignificance.MEDIUM,
                old_text=old,
                new_text=None,
                old_sentence_index=old_start + paired + offset,
            )
        )
    for offset, new in enumerate(new_items[paired:]):
        changes.append(
            _added_change(new, new_sentence_index=new_start + paired + offset)
        )
    return changes


def _added_change(sentence: str, *, new_sentence_index: int) -> VersionChange:
    lowered = sentence.lower()
    correction_markers = (
        "correction:",
        "corrected on",
        "this article was corrected",
        "this story has been updated",
        "updated on",
    )
    if any(marker in lowered for marker in correction_markers):
        return VersionChange(
            kind=VersionChangeKind.CORRECTION_NOTICE,
            significance=ChangeSignificance.HIGH,
            old_text=None,
            new_text=sentence,
            new_sentence_index=new_sentence_index,
        )
    return VersionChange(
        kind=VersionChangeKind.SENTENCE_ADDED,
        significance=ChangeSignificance.MEDIUM,
        old_text=None,
        new_text=sentence,
        new_sentence_index=new_sentence_index,
    )


def _summarize(changes: tuple[VersionChange, ...]) -> VersionDiff:
    added = sum(
        item.kind in {VersionChangeKind.SENTENCE_ADDED, VersionChangeKind.CORRECTION_NOTICE}
        for item in changes
    )
    removed = sum(item.kind is VersionChangeKind.SENTENCE_REMOVED for item in changes)
    replaced = sum(item.kind is VersionChangeKind.SENTENCE_REPLACED for item in changes)
    numeric = sum(item.kind is VersionChangeKind.NUMERIC_CHANGED for item in changes)
    temporal = sum(item.kind is VersionChangeKind.TEMPORAL_CHANGED for item in changes)
    material = sum(item.significance is not ChangeSignificance.LOW for item in changes)
    return VersionDiff(
        methodology_version=VERSION_DIFF_METHODOLOGY,
        changes=changes,
        added_count=added,
        removed_count=removed,
        replaced_count=replaced,
        numeric_change_count=numeric,
        temporal_change_count=temporal,
        material_change_count=material,
    )


def _normalized_quantities(values: tuple[dict[str, object], ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            item.get("kind"),
            item.get("normalized_value"),
            item.get("unit"),
            item.get("currency"),
        )
        for item in values
    )


def _normalized_temporal(values: tuple[dict[str, object], ...]) -> tuple[tuple[object, ...], ...]:
    return tuple((item.get("kind"), item.get("normalized"), item.get("raw")) for item in values)


def _norm(value: str) -> str:
    return " ".join(value.lower().split())
