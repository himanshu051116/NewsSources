"""Conservative, source-grounded editorial signals for short news editions."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from html import unescape
from typing import Literal
from urllib.parse import urlsplit

ReportType = Literal["news", "analysis", "opinion", "service", "archive"]
FreshnessStatus = Literal["current", "date_unconfirmed", "expired", "historical"]
UNAVAILABLE_EXCERPT = "Source text unavailable. Open the original report for details."
_STOP = frozenset(
    """a an the and or of to in on at for from with by as is are was were be
    has have had after before over amid into says said new latest live update updates
    का के की को में से पर और ने है हैं एक लिए भी यह इस उस तक अब आज होगा होगी
    """.split()
)
_BOILERPLATE = re.compile(
    r"(?:subscribe|subscription|sign\s*in|log\s*in|advertisement|read also|also read|"
    r"copyright|all rights reserved|accept cookies|privacy policy|follow us on|"
    r"download (?:our|the) app|published\s*(?:by|:)|updated\s*:|written by|"
    r"list \d+ of \d+|end of list|recommended stories|related (?:stories|articles)|"
    r"share this|listen to this|play video|"
    r"Getty Images|iStockphoto|photo credit|https?://|storyline \d+|"
    r"may god grant|thoughts and prayers|heartfelt condolences|deeply saddened|"
    r"बड़ा झटका दिया|दुनिया.*उजड़|"
    r"हिंदी न्यूज़|हिन्दी न्यूज़|होम न्यूज़|यह भी पढ़ें|ये भी पढ़ें|विज्ञापन)",
    re.I,
)
_PUBLIC_IMPACT = re.compile(
    r"\b(?:earthquake|floods?|cyclone|evacuat\w*|outage|blackout|ceasefire|"
    r"election|parliament|cabinet|supreme court|verdict|inflation|interest rates?|"
    r"tax(?:es)?|budget|unemployment|recall|outbreak|vaccine|public health|"
    r"data breach|cyberattack|peace talks|killed|deaths?|water supply|"
    r"championship|world cup|discovery|breakthrough|dearness allowance)\b|"
    r"भूकंप|भूकम्प|बाढ़|चक्रवात|चुनाव|संसद|महंगाई|ब्याज|बजट|"
    r"सुप्रीम कोर्ट|मौत|टीका|युद्धविराम|पेयजल|बिजली कटौती|विश्व कप",
    re.I,
)
_CLICKBAIT = re.compile(
    r"\b(?:you won't believe|will shock you|goes viral|viral video|must watch|"
    r"net worth|best deals?|discount code|what happens next|top \d+|"
    r"holiday mode|chaos collaborators|fans react|taunts?|jibe)\b|"
    r"होश उड़|हैरान रह|वायरल वीडियो|जानकर चौंक",
    re.I,
)
_QUALIFICATION = re.compile(
    r"\b(?:no|not|never|denies|denied|without|unconfirmed|alleged|may|might|could|"
    r"would|reportedly|unless|but|however|although|said|says|according|claimed|claims)\b|"
    r"नहीं|नही|इनकार|आरोप|कहा|बताया|लेकिन|हालांकि|हालाँकि|अगर|यदि|बिना|संभावना",
    re.I,
)
_NAV_PREFIX = re.compile(r"^(?:और\s*पढ़ें\s*[:|\u203a»—-]?\s*)+")
_SENTENCES = re.compile(r"(?<=[!?।])\s+|(?<=[.])\s+(?=[A-Z\u0900-\u097f])")
_WORDS = re.compile(r"\S+")


def plain(value: str) -> str:
    if "<" in value:
        value = re.sub(r"<[^>]+>", " ", value)
    if "&" in value:
        value = unescape(value)
    return " ".join(value.split())


@lru_cache(maxsize=24_000)
def headline_terms(value: str) -> frozenset[str]:
    # Preserve Devanagari combining marks, which Python's \w excludes.
    words = re.sub(r"[^\w\u0300-\u036f\u0900-\u097f]+", " ", plain(value).casefold()).split()
    return frozenset(word for word in words if len(word) > 1 and word not in _STOP)


def report_type(title: str, url: str) -> ReportType:
    try:
        path = urlsplit(url).path.casefold()
    except ValueError:
        path = ""
    if re.search(r"/(?:archives?|from-the-archives)(?:/|$)", path) or re.match(
        r"^from (?:the )?(?:[\w -]+ )?archives?\b", title, re.I,
    ):
        return "archive"
    if re.search(r"/(?:opinion|editorial|columns?)(?:/|$)", path) or re.match(
        r"^(?:(?:opinion|editorial)\s*[:|—-]|letters to (?:the )?editor|readers? write|संपादकीय)",
        title,
        re.I,
    ):
        return "opinion"
    if re.search(r"/(?:astrology|horoscope|shopping|deals|reviews?|utility)(?:/|$)", path) or re.search(
        r"\b(?:horoscope|rashifal|astrology|coupon|shopping deals|daily quiz|school assembly)\b|राशिफल|ज्योतिष",
        title,
        re.I,
    ):
        return "service"
    if re.search(r"/(?:explained|explainer|analysis)(?:/|$)", path) or re.match(
        r"^(?:explained|analysis)\s*[:|—-]",
        title,
        re.I,
    ):
        return "analysis"
    return "news"


def reporting_freshness(
    title: str, url: str, *, published_at: datetime, date_basis: str, as_of: datetime,
) -> tuple[FreshnessStatus, str | None]:
    """Flag clear expiry signals without treating recent reporting about history as stale.

    Publication-window filtering happens in SQL. This additional gate handles
    undated captures and dated, time-sensitive pages retained in the longer stream.
    It is evaluated against the edition snapshot, including during pagination.
    """
    if report_type(title, url) == "archive":
        return "historical", "This is an archive reprint, rather than a current development."
    if date_basis != "published":
        return "date_unconfirmed", "Capture time is known; the original publication date is not confirmed."
    sensitive = re.search(
        r"\b(?:live\s*(?:blog|updates?|scores?|stream|commentary)|horoscope|rashifal|"
        r"weather forecast|daily quiz|school assembly|today[’']?s (?:weather|quiz))\b|"
        r"राशिफल|आज का मौसम|लाइव\s*(?:अपडेट|स्कोर|ब्लॉग)", title + " " + url, re.I,
    )
    if sensitive:
        # Dates in a live/dated-service headline identify the session it covers.
        # An ordinary report's historical background does not trigger this rule.
        explicit: list[date] = []
        for year, month, day in re.findall(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", title):
            try:
                explicit.append(date(int(year), int(month), int(day)))
            except ValueError:
                continue
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            "जनवरी": 1, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
            "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10, "नवंबर": 11, "दिसंबर": 12,
        }
        month_pattern = r"(?:Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*|जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर)"
        matches = [(day, month, year) for day, month, year in re.findall(
            rf"\b(\d{{1,2}})\s+({month_pattern})(?:,?\s+(20\d{{2}}))?", title, re.I)]
        matches += [(day, month, year) for month, day, year in re.findall(
            rf"\b({month_pattern})\s+(\d{{1,2}})(?:,?\s+(20\d{{2}}))?", title, re.I)]
        for day, month, year in matches:
            key = month.casefold() if month in months else month[:3].casefold()
            try:
                value = date(int(year) if year else published_at.year, months[key], int(day))
                # December's yearless heading rediscovered in January.
                if not year and value > published_at.date() + timedelta(days=180):
                    value = value.replace(year=value.year - 1)
                explicit.append(value)
            except (KeyError, ValueError):
                continue
        if explicit and max(explicit) < as_of.date():
            return "expired", "The dated live session or daily service in this headline has ended."
        if as_of - published_at >= timedelta(hours=36):
            return "expired", "This live session or daily service was published more than 36 hours before this edition."
    return "current", None


def conflicting_details(first: str, second: str) -> bool:
    """Do not present differing reported numbers or qualifications as one account."""
    first_numbers = set(re.findall(r"\d+(?:[.,]\d+)*", first))
    second_numbers = set(re.findall(r"\d+(?:[.,]\d+)*", second))
    qualifiers = {"no", "not", "denies", "denied", "alleged", "unconfirmed", "नहीं", "इनकार"}
    return bool(
        (first_numbers and second_numbers and first_numbers != second_numbers)
        or (headline_terms(first) & qualifiers) != (headline_terms(second) & qualifiers)
    )


def excerpt_sentence(text: str, title: str, published_year: int | None = None) -> str | None:
    """Choose an intact source sentence that adds information beyond the headline.

    No sentences from different reports are combined; attribution, uncertainty and
    numbers stay in the publisher's wording. Clipping is handled by the caller.
    """
    title_words = headline_terms(title)
    title_key = plain(title).casefold().rstrip(".!।")
    # A short excerpt must identify the headline's subject. In sentence-case
    # headlines, a leading multiword name is a strong anchor; related background
    # about another person must not stand in for that subject. Title-case headlines
    # do not supply the same signal, and later location names are not the subject.
    prefix = " ".join(plain(title).split()[:6])
    capitalized = re.findall(r"\b[A-Z][a-z]+\b", prefix)
    anchors = re.findall(r"\b(?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+\b", prefix)
    initial_names = re.findall(r"\b(?:[A-Z]\.\s*)+[A-Z][a-z]+\b", prefix)
    if initial_names:
        anchors = initial_names
    anchor_words = {word.casefold() for name in anchors for word in name.split()
                    if word.casefold() not in {"sir", "the", "a", "an"}}
    if len(capitalized) >= max(4, len(prefix.split()) - 1):
        anchor_words = set()
    candidates: list[tuple[float, int, str]] = []
    text = re.sub(r"(?<=[a-z])\.(?=[A-Z][a-z])", ". ", unescape(text[:6000]))
    for paragraph in re.split(r"\n+", text):
        paragraph = plain(paragraph)
        if not paragraph:
            continue
        sentences = _SENTENCES.split(paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            # Some captures join a navigation control directly to the next
            # Hindi paragraph; retain the report while removing that prefix.
            sentence = _NAV_PREFIX.sub("", sentence)
            index = len(candidates)
            if len(sentence) < 35 or len(sentence.split()) < 6 or _BOILERPLATE.search(sentence):
                continue
            if sentence.endswith("?"):
                continue
            # Captions and player metadata often have no sentence ending, or
            # repeat the same caption inside one apparent paragraph.
            if not sentence.rstrip('\"\'”’)] ').endswith((".", "!", "।")):
                continue
            tokens = sentence.casefold().split()
            phrases = [tuple(tokens[i:i + 6]) for i in range(len(tokens) - 5)]
            if len(phrases) != len(set(phrases)):
                continue
            years = {int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", sentence)}
            title_years = {int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", title)}
            if published_year and years and max(years) < published_year - 1 and not title_years:
                continue
            # The display clips at 30 words / 240 characters. A qualification or
            # attribution after that cut can reverse the apparent meaning. Use
            # another sentence, or show no excerpt, instead of dropping it.
            word_spans = list(_WORDS.finditer(sentence[:241]))
            cut = min(240, word_spans[30].start() if len(word_spans) > 30 else len(sentence))
            if cut < len(sentence) and not sentence[cut].isspace():
                cut = sentence.rfind(" ", 0, cut) + 1
            if _QUALIFICATION.search(sentence[cut:]):
                continue
            words = headline_terms(sentence)
            if anchor_words and not (words & anchor_words):
                continue
            if not words or sentence.casefold().rstrip(".!।") == title_key:
                continue
            if title_key and sentence.casefold().startswith(title_key):
                continue
            added = words - title_words
            if len(title_words) >= 4 and len(sentence.split()) <= 8 and len(added) < 3:
                continue
            if title_words and len(added) < 2 and len(words & title_words) / len(words) > 0.8:
                continue
            score = 3.0 - min(index, 20) * 0.18
            overlap = len(words & title_words)
            if len(title_words) >= 4 and overlap == 0:
                continue
            score += min(overlap, 4) * 0.45
            score -= 1.2 if len(title_words) >= 4 and overlap < 2 else 0
            score += 0.6 if re.search(r"\d", sentence) else 0
            score += (
                0.4
                if re.search(r"\b(?:said|according|reported|confirmed)\b|कहा|बताया", sentence, re.I)
                else 0
            )
            score += (
                0.7
                if re.search(
                    r"\b(?:may|might|alleged|unconfirmed|preliminary|at least|not confirmed)\b|"
                    r"आरोप|संभावना|पुष्टि नहीं|कम से कम",
                    sentence,
                    re.I,
                )
                else 0
            )
            score += 0.5 if len(sentence.split()) <= 30 and len(sentence) <= 240 else -0.5
            score -= (
                2
                if re.match(
                    r"^(?:he|she|it|they|this|these|those|however)\b|^(?:उन्होंने|इससे|यहां)\b",
                    sentence,
                    re.I,
                )
                else 0
            )
            candidates.append((score, -index, sentence))
            if len(candidates) >= 8:
                break
        if len(candidates) >= 8:
            break
    return max(candidates, default=(0, 0, None))[2]


EXCERPT_POLICY = "digest-excerpt-v5"


def prepare_excerpt(text: str, title: str, published_year: int) -> dict[str, object]:
    """Derived, version-scoped metadata; original reporting is never rewritten."""
    return {"policy": EXCERPT_POLICY, "year": published_year,
            "sentence": excerpt_sentence(text, title, published_year)}


def prepared_excerpt(value: object, published_year: int) -> tuple[bool, str | None]:
    if isinstance(value, dict) and value.get("policy") == EXCERPT_POLICY \
            and value.get("year") == published_year:
        sentence = value.get("sentence")
        if sentence is None or isinstance(sentence, str) and len(sentence) <= 6000:
            return True, sentence
    return False, None


def brief_development_key(title: str, explanation: str) -> str | None:
    """High-confidence bilingual anchors for a known repeated announcement.

    This is deliberately bounded, not a general translation or event matcher.
    Full reports remain separate; only a short-edition slot can be shared.
    """
    text = (title + " " + explanation).casefold()
    if re.search(r"\b(?:not|denied|denies|proposed|proposal)\b|नहीं|प्रस्ताव", text):
        return None
    if not re.search(r"dearness allowance|महंगाई\s*भत्त", text):
        return None
    if not re.search(r"central government|केंद्र|केन्द्र", text):
        return None
    if not re.search(r"employees|pensioners|कर्मचार|पेंशन", text):
        return None
    if not re.search(r"\b(?:approved|cleared)\b|मंजूरी|स्वीकृति", text):
        return None
    percentages = {str(Decimal(value.replace(",", ".")).normalize()) for value in re.findall(
        r"(\d+(?:[.,]\d+)?)\s*(?:%|percentage\s*points?|per\s*cent|percent|फीसदी|प्रतिशत)", text)}
    return "india-central-da-approved:" + next(iter(percentages)) if len(percentages) == 1 else None


def same_development(
    first_title: str, first_text: str, second_title: str, second_text: str
) -> bool:
    """Merge near-identical coverage, preserving different numbers and denials."""
    first, second = headline_terms(first_title), headline_terms(second_title)
    if min(len(first), len(second)) < 6:
        return False
    if len(first & second) / len(first | second) < 0.80:
        return False

    def numbers(value: str) -> set[str]:
        return set(re.findall(r"\d+(?:[.,]\d+)*", value))

    if numbers(first_title) != numbers(second_title):
        return False
    qualifiers = {"no", "not", "denies", "denied", "alleged", "नहीं", "इनकार"}
    if (first & qualifiers) != (second & qualifiers):
        return False
    first_body, second_body = headline_terms(first_text[:600]), headline_terms(second_text[:600])
    return bool(
        first_body
        and second_body
        and not conflicting_details(first_text[:600], second_text[:600])
        and len(first_body & second_body) / len(first_body | second_body) >= 0.55
    )


def public_interest_score(title: str, kind: ReportType) -> float:
    """Heuristic prominence, never a truth or publisher-reputation score."""
    return (
        min(len(_PUBLIC_IMPACT.findall(title)), 3) * 0.9
        - (1.8 if _CLICKBAIT.search(title) else 0)
        - (1.2 if kind == "opinion" else 0)
    )
