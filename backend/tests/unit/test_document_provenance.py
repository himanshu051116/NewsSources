"""PDF claim anchors must be unique, byte-grounded, and non-verifying."""
from hashlib import sha256

from newsintel.domain.intelligence.document_provenance import locate_pdf_source_sentence


def _page(text: str, page: int, start: int, *, ocr: bool = False) -> dict:
    return {
        "page": page,
        "source_url": f"https://example.org/report.pdf#page={page}",
        "char_start": start,
        "char_end": start + len(text),
        "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "extraction_method": "ocr_tesseract" if ocr else "pdf_native_text",
        "ocr_unverified": ocr,
    }


def test_exact_source_sentence_maps_to_correct_page_offsets() -> None:
    first = "Introductory overview."
    second = "Officials said 31 people were injured in the incident."
    text = first + "\n\n" + second
    hit = locate_pdf_source_sentence(
        text, [_page(first, 1, 0), _page(second, 2, len(first) + 2)],
        second,
    )
    assert hit is not None
    assert hit["page"] == 2
    assert hit["char_start"] == len(first) + 2
    assert hit["char_end"] == len(text)
    assert hit["page_url"].endswith("#page=2")
    assert hit["independent_confirmation"] is False


def test_matches_layout_whitespace_without_guessing_words() -> None:
    text = "The authority stated\nthat 25 sites were inspected."
    hit = locate_pdf_source_sentence(
        text, [_page(text, 1, 0)],
        "The authority stated that 25 sites were inspected.",
    )
    assert hit is not None and text[hit["char_start"]:hit["char_end"]] == text


def test_duplicate_passages_do_not_invent_one_page_citation() -> None:
    phrase = "The authority said the report would be published."
    text = phrase + "\n\n" + phrase
    assert locate_pdf_source_sentence(
        text, [_page(phrase, 1, 0), _page(phrase, 2, len(phrase) + 2)],
        phrase,
    ) is None


def test_no_match_when_page_sha_is_wrong_or_sentence_crosses_pages() -> None:
    first, second = "The agency published", " a detailed inspection report."
    text = first + "\n\n" + second
    good = [_page(first, 1, 0), _page(second, 2, len(first) + 2)]
    assert locate_pdf_source_sentence(text, good, "The agency published a detailed inspection report.") is None
    bad = [_page(text, 1, 0)]
    bad[0]["text_sha256"] = "0" * 64
    assert locate_pdf_source_sentence(text, bad, text) is None


def test_ocr_anchor_remains_explicitly_unverified() -> None:
    phrase = "Officials reported 35 registered incidents in April."
    hit = locate_pdf_source_sentence(
        phrase, [_page(phrase, 1, 0, ocr=True)], phrase,
    )
    assert hit is not None
    assert hit["ocr_unverified"] is True
    assert hit["independent_confirmation"] is False
