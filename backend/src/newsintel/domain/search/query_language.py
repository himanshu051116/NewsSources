from __future__ import annotations

import unicodedata


def normalize_query(value: str) -> str:
    """Normalize analyst query text without changing lexical intent."""
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.split())


def detect_script(value: str) -> str:
    has_latin = False
    has_devanagari = False
    has_other_letter = False
    for char in value:
        if not char.isalpha():
            continue
        code = ord(char)
        if 0x0900 <= code <= 0x097F:
            has_devanagari = True
        elif "LATIN" in unicodedata.name(char, ""):
            has_latin = True
        else:
            has_other_letter = True
    families = sum(bool(item) for item in (has_latin, has_devanagari, has_other_letter))
    if families > 1:
        return "mixed"
    if has_devanagari:
        return "devanagari"
    if has_latin:
        return "latin"
    if has_other_letter:
        return "other"
    return "unknown"


def language_filter_hint(script: str) -> str | None:
    # Script alone is not a reliable language identifier: Devanagari can be
    # Hindi, Marathi, Nepali, Sanskrit, or another language. The search UI may
    # show script-aware help, but it must never infer a language filter from
    # script alone.
    _ = script
    return None


def use_english_stemming(query: str, language: str | None) -> bool:
    if language and language.lower() not in {"en", "eng", "en-us", "en-gb"}:
        return False
    return detect_script(query) == "latin"
