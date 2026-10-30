"""Short source-grounded editions and account-owned reading streams.

This intentionally uses captured reporting, without an LLM or remote fallback.
The two-minute edition is a selection; the longer stream exposes its coverage.
"""
from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.digest_quality import (
    UNAVAILABLE_EXCERPT,
    FreshnessStatus,
    ReportType,
    brief_development_key,
    conflicting_details,
    excerpt_sentence,
    headline_terms,
    plain,
    prepared_excerpt,
    public_interest_score,
    report_type,
    reporting_freshness,
    same_development,
)
from newsintel.domain.intelligence.topics import classify_news_topic
from newsintel.infrastructure.db.models import (
    ArticleModel,
    ArticleVersionModel,
    PlatformUserModel,
    PublisherModel,
)

TOPICS = {
    "business_finance": "Business & economy",
    "politics_government": "Politics & government",
    "law_justice": "Law & justice",
    "science_health": "Science & health",
    "technology": "Technology",
    "climate_environment": "Climate & environment",
    "security_conflict": "Security & conflict",
    "sports": "Sports",
    "education": "Education",
    "entertainment": "Entertainment & culture",
    "lifestyle": "Lifestyle",
    "general": "Other news",
}
_EXTRA_TERMS = {
    "lifestyle": ("horoscope", "astrology", "rashifal", "राशिफल", "ज्योतिष", "राशियों"),
    "education": ("education", "school", "university", "exam", "student", "शिक्षा", "परीक्षा"),
    "entertainment": ("cinema", "film", "movie", "actor", "music", "फिल्म", "सिनेमा"),
    "business_finance": ("अर्थव्यवस्था", "महंगाई", "बाजार", "व्यापार"),
    "politics_government": ("सरकार", "चुनाव", "संसद", "मंत्री"),
    "law_justice": ("अदालत", "न्यायालय", "फैसला"),
    "science_health": ("स्वास्थ्य", "अस्पताल", "वैक्सीन", "वैज्ञानिक"),
    "technology": ("तकनीक", "प्रौद्योगिकी", "सॉफ्टवेयर"),
    "climate_environment": ("मौसम", "जलवायु", "प्रदूषण", "बारिश", "भूकंप", "earthquake",
                            "leopard", "wildlife", "tiger", "forest", "भूकम्प"),
    "security_conflict": ("सेना", "हमला", "युद्ध"),
    "sports": ("क्रिकेट", "खेल", "फुटबॉल"),
}
_EXTRA_PATTERNS = {
    key: re.compile(r"(?<![a-z0-9])(?:" + "|".join(map(re.escape, terms)) + r")(?![a-z0-9])")
    for key, terms in _EXTRA_TERMS.items()
}
MAX_REPORTS = 6000
WORD_BUDGET = 360  # leaves room for dates and interface text at 200 words/minute
STREAMS_KEY = "news_digest_streams"
PREFERENCES_KEY = "news_digest_preferences"
Term = Annotated[str, Field(min_length=1, max_length=100)]


class DigestFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topics: list[Term] = Field(default_factory=list, max_length=len(TOPICS))
    publisher_ids: list[UUID] = Field(default_factory=list, max_length=200)
    languages: list[Annotated[str, Field(min_length=1, max_length=35)]] = Field(
        default_factory=list, max_length=30,
    )
    keywords: list[Term] = Field(default_factory=list, max_length=20)
    exclude_keywords: list[Term] = Field(default_factory=list, max_length=20)

    @field_validator("topics", "languages", "keywords", "exclude_keywords")
    @classmethod
    def normalized_terms(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.casefold() for value in values))

    @field_validator("topics")
    @classmethod
    def known_topics(cls, values: list[str]) -> list[str]:
        if any(value not in TOPICS for value in values):
            raise ValueError("Unknown news topic")
        return values

    @field_validator("publisher_ids")
    @classmethod
    def unique_publishers(cls, values: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(values))


class DigestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Literal["daily", "weekly"] = "daily"
    filters: DigestFilters = Field(default_factory=DigestFilters)
    as_of: datetime | None = None
    full_stream: bool = False
    current_only: bool = False
    offset: int = Field(default=0, ge=0, le=MAX_REPORTS)
    page_size: int = Field(default=50, ge=1, le=100)

    @field_validator("as_of")
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("as_of must include a timezone")
        return value


class DigestSource(BaseModel):
    publisher_id: UUID
    publisher_name: str
    article_id: UUID
    url: str | None


class DigestItem(BaseModel):
    article_id: UUID
    event_id: UUID | None
    title: str
    explanation: str
    topic: str
    language: str
    published_at: datetime
    date_basis: Literal["published", "first_captured"]
    sources: list[DigestSource]
    report_count: int
    report_type: ReportType = "news"
    summary_available: bool = True
    freshness_status: FreshnessStatus = "current"
    freshness_reason: str | None = None


class DigestEdition(BaseModel):
    period: str
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    filters: DigestFilters
    items: list[DigestItem]
    word_count: int
    estimated_read_seconds: int
    full_stream: bool
    current_only: bool = False
    eligible_reports: int
    scanned_reports: int
    matching_reports: int
    excluded_non_reports: int
    story_count: int
    publisher_count: int
    sampled: bool
    next_offset: int | None
    latest_capture_at: datetime | None
    selected_publisher_count: int = 0
    selected_days: int = 0
    unavailable_summaries: int = 0
    excluded_stale_or_uncertain: int = 0


class StreamInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    period: Literal["daily", "weekly"] = "daily"
    filters: DigestFilters = Field(default_factory=DigestFilters)


class SavedStream(StreamInput):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ReadingPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Literal["daily", "weekly"] = "daily"
    filters: DigestFilters = Field(default_factory=DigestFilters)
    stream_id: UUID | None = None


def clean_text(value: str) -> str:
    return plain(value)


def word_count(value: str) -> int:
    # Count CJK characters separately; whitespace splitting alone would undercount them.
    cjk = re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", value)
    rest = re.sub(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", " ", value)
    return len(cjk) + len(rest.split())


def clip_text(value: str, *, words: int, chars: int) -> str:
    value = clean_text(value)
    if word_count(value) <= words and len(value) <= chars:
        return value
    end = min(len(value), chars)
    while end > 0 and word_count(value[:end]) > words:
        end -= 1
    clipped = value[:end].rstrip()
    if end < len(value) and not value[end:end + 1].isspace() and " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(".,;:…") + "…"


@lru_cache(maxsize=8192)
def source_line(text: str, title: str, published_year: int | None = None) -> str:
    """Extract a useful source sentence without inventing or combining claims."""
    sentence = excerpt_sentence(text, title, published_year)
    return clip_text(sentence, words=30, chars=240) if sentence else UNAVAILABLE_EXCERPT


@lru_cache(maxsize=8192)
def news_topic(text: str, context: str = "", url: str = "") -> str:
    # Criminal proceedings are the subject even when a hospital, financial
    # adviser or sports personality appears incidentally in the captured body.
    if re.search(r"\b(?:arrested|sentenced|convicted|murder|sexually assault\w*)\b|"
                 r"गिरफ्तार|हत्या|सजा|यौन उत्पीड़न", text, re.I) or (
        re.search(r"\bpolice\b", text, re.I)
        and re.search(r"\b(?:death|killing|crime)\b", text, re.I)
    ):
        return "law_justice"
    # Publisher section names are useful when a headline uses only names or allusions.
    sections = {
        "entertainment": "entertainment", "movies": "entertainment", "cinema": "entertainment",
        "bollywood": "entertainment", "kollywood": "entertainment", "music": "entertainment",
        "sports": "sports", "sport": "sports", "cricket": "sports", "football": "sports",
        "technology": "technology", "tech": "technology", "gadgets": "technology",
        "business": "business_finance", "economy": "business_finance",
        "markets": "business_finance",
        "politics": "politics_government", "education": "education", "health": "science_health",
        "science": "science_health", "environment": "climate_environment",
        "weather": "climate_environment", "astrology": "lifestyle", "horoscope": "lifestyle",
    }
    try:
        parts = urlsplit(url).path.casefold().split("/")
    except ValueError:
        parts = []
    for part in parts:
        if part in sections:
            return sections[part]
    # The headline wins over incidental terms in navigation or related-story links.
    for candidate in (text, clean_text(context)[:500]):
        lowered = candidate.casefold()
        for key, pattern in _EXTRA_PATTERNS.items():
            if pattern.search(lowered):
                # A university or student is often the actor, not the subject:
                # preserve explicit election/health reporting in those headlines.
                if key == "education" and re.search(r"\b(?:student|university)\b", lowered):
                    classified = classify_news_topic(candidate).topic_key
                    political_rally = classified == "politics_government" and re.search(
                        r"\b(?:rally|protest|national|general)\b", lowered,
                    ) and re.search(r"\b(?:election|parliament|government)\b", lowered)
                    if (classified == "science_health" or political_rally) and not re.search(
                        r"\b(?:school|education|exam|admission|tuition|curriculum)\b", lowered,
                    ):
                        return classified
                return key
        classified = classify_news_topic(candidate).topic_key
        if classified != "general":
            return classified
    return "general"


def is_reporting_page(row: dict[str, Any]) -> bool:
    """Keep common utility/listing captures out of news editions, without deleting them."""
    try:
        path = urlsplit(row["url"]).path.casefold()
    except ValueError:
        return False
    if re.search(r"/(?:tools-and-calculators|calculators|topics?|tags?|authors?|search)(?:/|$)",
                 path):
        return False
    if row["date_basis"] == "first_captured":
        if re.search(r"(?:^|[-/])(?:emi|loan|bmi|age|tax)-calculator(?:/|$)", path):
            return False
        title = clean_text(row["title"]).casefold()
        if re.search(
            r"(?:latest .*(?:news|reviews|updates)|news in hindi|tips and tricks in hindi)", title,
        ):
            return False
    return True


def safe_source_url(value: str) -> str | None:
    return value if re.match(r"^https?://[^\s]+$", value, re.IGNORECASE) else None


def group_reports(rows: list[dict[str, Any]], filters: DigestFilters, *,
                  as_of: datetime | None = None) -> list[DigestItem]:
    """Group identities and conservatively similar reporting, retaining every source."""
    groups: dict[str, list[dict[str, Any]]] = {}
    title_index: dict[tuple[str, str], set[str]] = {}
    # Exact content/title identities can join a group even when event assignment differs.
    aliases: dict[str, str] = {}
    snapshot_time = as_of or max((row["published_at"] for row in rows), default=datetime.now(UTC))
    for row in rows:
        if not is_reporting_page(row):
            continue
        text = f"{row['title']} {row['text']}"
        lowered = text.casefold()
        topic = news_topic(row["title"], row["text"], row["url"])
        if filters.topics and topic not in filters.topics:
            continue
        if filters.keywords and not any(term in lowered for term in filters.keywords):
            continue
        if any(term in lowered for term in filters.exclude_keywords):
            continue
        prepared, sentence = prepared_excerpt(row.get("prepared_excerpt"), row["published_at"].year)
        explanation = ((clip_text(sentence, words=30, chars=240) if sentence else UNAVAILABLE_EXCERPT)
                       if prepared else source_line(row["text"], row["title"], row["published_at"].year))
        quality = row.get("extraction_quality")
        usable = explanation != UNAVAILABLE_EXCERPT and not (
            isinstance(quality, (int, float)) and quality < .35
        )
        kind = report_type(row["title"], row["url"])
        freshness, reason = reporting_freshness(row["title"], row["url"],
            published_at=row["published_at"], date_basis=row["date_basis"], as_of=snapshot_time)
        row = dict(row, topic=topic, explanation=explanation, summary_available=usable,
                   report_type=kind, freshness_status=freshness, freshness_reason=reason)
        title_key = re.sub(r"[^\w\u0300-\u036f\u0900-\u097f]+", " ",
                           clean_text(row["title"]).casefold()).strip()
        keys = ["article:" + str(row["article_id"])]
        if len(title_key) >= 20:
            keys.append("title:" + kind + ":" + title_key)
        if row.get("content_hash") and len(clean_text(row["text"])) >= 80:
            keys.append("content:" + kind + ":" + row["content_hash"])
        existing = list(dict.fromkeys(aliases[key] for key in keys if key in aliases))
        # An identical headline is not proof that two reports agree. Counts and
        # denials can change while publishers keep their original headline.
        existing = [other for other in existing if not any(
            conflicting_details(row["title"], previous["title"])
            or (usable and previous["summary_available"]
                and conflicting_details(explanation, previous["explanation"]))
            for previous in groups[other]
        )]
        title_terms = headline_terms(row["title"])
        row["title_terms"] = title_terms
        if not existing and len(title_terms) >= 6:
            # Common words are poor matching keys. Bound each bucket so a large
            # period of templated headlines cannot turn this into an all-pairs scan.
            buckets = [title_index.get((row["language"], term), set()) for term in title_terms]
            possible = set().union(*(bucket for bucket in sorted(buckets, key=len)[:6]
                                     if len(bucket) <= 200))
            shared_terms = [(other, len(title_terms & groups[other][0]["title_terms"]))
                            for other in possible if other in groups]
            for other, shared in sorted(shared_terms, key=lambda pair: (-pair[1], pair[0]))[:80]:
                if shared < 6:
                    continue
                reference = groups[other][0]
                if kind == reference["report_type"] and same_development(row["title"], row["text"],
                                    reference["title"], reference["text"]):
                    existing = [other]
                    break
        group_key = existing[0] if existing else keys[0]
        for other in existing[1:]:
            groups[group_key].extend(groups.pop(other))
            for alias, target in list(aliases.items()):
                if target == other:
                    aliases[alias] = group_key
        groups.setdefault(group_key, []).append(row)
        for key in keys:
            aliases[key] = group_key
        for term in title_terms:
            title_index.setdefault((row["language"], term), set()).add(group_key)
    items = []
    for group in groups.values():
        group.sort(key=lambda row: (
            row["freshness_status"] != "current",
            not row["summary_available"], -row["published_at"].timestamp(), str(row["article_id"]),
        ))
        lead = group[0]
        sources: dict[UUID, DigestSource] = {}
        for row in group:
            sources.setdefault(row["publisher_id"], DigestSource(
                publisher_id=row["publisher_id"], publisher_name=row["publisher_name"],
                article_id=row["article_id"], url=safe_source_url(row["url"]),
            ))
        # Put the excerpt's publisher first, so attribution is never ambiguous.
        ordered_sources = [sources.pop(lead["publisher_id"]), *sources.values()]
        items.append(DigestItem(
            article_id=lead["article_id"], event_id=lead["event_id"],
            # A headline's final clause may carry a denial or attribution.
            # Preserve it; the edition word budget already includes full titles.
            title=clean_text(lead["title"]),
            explanation=lead["explanation"] if lead["summary_available"] else UNAVAILABLE_EXCERPT,
            topic=lead["topic"],
            language=lead["language"], published_at=lead["published_at"],
            date_basis=lead["date_basis"], sources=ordered_sources, report_count=len(group),
            report_type=lead["report_type"],
            summary_available=lead["summary_available"],
            freshness_status=lead["freshness_status"], freshness_reason=lead["freshness_reason"],
        ))
    return sorted(items, key=lambda item: (item.published_at, str(item.article_id)), reverse=True)


def item_words(item: DigestItem) -> int:
    return word_count(" ".join((item.title, item.explanation, TOPICS[item.topic],
                                item.sources[0].publisher_name)))


def short_edition(items: list[DigestItem], *, period: str = "daily",
                  as_of: datetime | None = None, filters: DigestFilters | None = None,
                  ) -> list[DigestItem]:
    """Choose useful developments before variety, with a distinct weekly time balance."""
    reference = as_of or max((item.published_at for item in items), default=datetime.now(UTC))
    filters = filters or DigestFilters()
    allow_service = bool(filters.keywords or filters.topics)
    start = reference - timedelta(days=7 if period == "weekly" else 1)
    remaining = [item for item in items if item.summary_available
                 and item.freshness_status == "current" and item.date_basis == "published"
                 and start <= item.published_at <= reference
                 and (item.report_type not in {"service", "opinion", "archive"} or allow_service)]
    scores: dict[UUID, float] = {}
    terms = {item.article_id: headline_terms(item.title) for item in remaining}
    developments = {item.article_id: brief_development_key(item.title, item.explanation)
                    for item in remaining}
    sizes = {item.article_id: item_words(item) for item in remaining}
    timestamps = {item.article_id: item.published_at.timestamp() for item in remaining}
    for item in remaining:
        age_hours = max(0, (reference - item.published_at).total_seconds() / 3600)
        freshness = (1 if period == "weekly" else 3) * math.exp(
            -age_hours / (120 if period == "weekly" else 18))
        scores[item.article_id] = (
            4 + public_interest_score(item.title, item.report_type) + freshness
            + min(1.8, math.log2(len(item.sources)) * .9)
            - (1.5 if item.date_basis == "first_captured" else 0)
        )
    chosen: list[DigestItem] = []
    topics: Counter[str] = Counter()
    publishers: Counter[UUID] = Counter()
    days: Counter[str] = Counter()
    similar_counts: Counter[UUID] = Counter()
    words = 0
    while remaining and len(chosen) < 12:
        # Once the remaining word budget is small, discard non-fitting stories
        # together. Re-ranking and rejecting them one by one is quadratic.
        remaining = [item for item in remaining if sizes[item.article_id] <= WORD_BUDGET-words]
        if not remaining:
            break

        def rank(item: DigestItem) -> tuple[float, float, str]:
            score = (scores[item.article_id] - topics[item.topic] * 1.6
                     - publishers[item.sources[0].publisher_id] * .7
                     - similar_counts[item.article_id] * 3
                     - (days[item.published_at.date().isoformat()] * 1.4
                        if period == "weekly" else 0))
            return -score, -timestamps[item.article_id], str(item.article_id)

        index = min(range(len(remaining)), key=lambda i: rank(remaining[i]))
        candidate = remaining.pop(index)
        # Keep competing updates in More headlines, rather than spending the brief
        # repeatedly covering one development. A shared broad event alone is insufficient.
        vocabulary = terms[candidate.article_id]
        following = []
        for other in remaining:
            if developments[candidate.article_id] is not None \
                    and developments[candidate.article_id] == developments[other.article_id] \
                    and abs((candidate.published_at-other.published_at).total_seconds()) <= 36*3600:
                continue
            shared = len(vocabulary & terms[other.article_id])
            union = len(vocabulary | terms[other.article_id])
            overlap = shared/union if union else 0
            if candidate.event_id is not None and candidate.event_id == other.event_id \
                    and shared >= 5 and overlap >= .55:
                continue
            if overlap >= .45:
                similar_counts[other.article_id] += 1
            following.append(other)
        remaining = following
        chosen.append(candidate)
        words += sizes[candidate.article_id]
        topics[candidate.topic] += 1
        publishers[candidate.sources[0].publisher_id] += 1
        days[candidate.published_at.date().isoformat()] += 1
    return chosen


def _saved_streams(metadata: dict[str, object]) -> list[SavedStream]:
    values = metadata.get(STREAMS_KEY, [])
    if not isinstance(values, list):
        raise ValueError("Saved stream metadata must be a list")
    return [SavedStream.model_validate(value) for value in values]


class NewsDigestService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def options(self) -> dict[str, Any]:
        async with self._sessions() as session:
            publishers = (await session.execute(select(PublisherModel.id, PublisherModel.name)
                          .order_by(PublisherModel.name, PublisherModel.id))).all()
            languages = (await session.scalars(select(ArticleModel.language).distinct()
                         .order_by(ArticleModel.language))).all()
        return {"topics": [{"key": key, "label": label} for key, label in TOPICS.items()],
                "publishers": [{"id": key, "name": name} for key, name in publishers],
                "languages": sorted({value.casefold() if value else "unknown"
                                     for value in languages})}

    async def edition(self, command: DigestRequest) -> DigestEdition:
        now = datetime.now(UTC)
        end = command.as_of.astimezone(UTC) if command.as_of else now
        if end > now:
            raise ValueError("The edition time cannot be in the future")
        start = end - timedelta(days=1 if command.period == "daily" else 7)
        # A single captured version per report, as known at the snapshot time.
        latest = (select(
            ArticleVersionModel.article_id, ArticleVersionModel.id.label("version_id"),
            ArticleVersionModel.title,
            ArticleVersionModel.language, ArticleVersionModel.published_at,
        ).where(ArticleVersionModel.created_at <= end)
          .distinct(ArticleVersionModel.article_id)
          .order_by(ArticleVersionModel.article_id, ArticleVersionModel.version_number.desc())
          .subquery())
        # The article row may contain legacy feed/sitemap modification dates.
        # Only the selected captured version can establish publication evidence.
        published = func.coalesce(latest.c.published_at, ArticleModel.first_observed_at)
        language = func.lower(func.coalesce(latest.c.language, ArticleModel.language, "unknown"))
        # Sample across the week as well as publishers when the capture limit is reached.
        partitions = [ArticleModel.publisher_id]
        if command.period == "weekly":
            partitions.append(func.date_trunc("day", published))
        query = (select(
            ArticleModel.id.label("article_id"), ArticleModel.event_id,
            ArticleModel.publisher_id, PublisherModel.name.label("publisher_name"),
            ArticleModel.canonical_url.label("url"),
            func.coalesce(latest.c.title, ArticleModel.title).label("title"),
            latest.c.version_id, language.label("language"),
            published.label("published_at"), ArticleModel.first_observed_at,
            latest.c.published_at.is_not(None).label("has_publication_date"),
            func.row_number().over(partition_by=partitions,
                order_by=(published.desc(), ArticleModel.id.desc())).label("source_rank"),
        ).join(PublisherModel, PublisherModel.id == ArticleModel.publisher_id)
          .outerjoin(latest, latest.c.article_id == ArticleModel.id)
          .where(published >= start, published < end, ArticleModel.created_at <= end))
        filters = command.filters
        if filters.publisher_ids:
            query = query.where(ArticleModel.publisher_id.in_(filters.publisher_ids))
        if filters.languages:
            query = query.where(language.in_(filters.languages))
        candidates = query.subquery()
        # Rank/count narrow rows first. Fetching body text before DISTINCT/window
        # sorting needlessly detoasts and sorts every historical article version.
        sample = (select(candidates, func.count().over().label("eligible_count"))
                  .order_by(candidates.c.source_rank, candidates.c.published_at.desc(),
                            candidates.c.article_id.desc()).limit(MAX_REPORTS).subquery())
        async with self._sessions() as session:
            # One SQL statement gives counts and rows the same PostgreSQL snapshot.
            rows = (await session.execute(select(
                sample, func.coalesce(func.left(ArticleVersionModel.text_content, 6000), "")
                    .label("text"), ArticleVersionModel.content_sha256.label("content_hash"),
                ArticleVersionModel.metadata_["extraction_quality_score"].label("extraction_quality"),
                ArticleVersionModel.metadata_["digest_excerpt"].label("prepared_excerpt"),
            ).outerjoin(ArticleVersionModel, ArticleVersionModel.id == sample.c.version_id)
              .order_by(sample.c.source_rank, sample.c.published_at.desc(),
                        sample.c.article_id.desc()))).mappings().all()
        eligible = rows[0]["eligible_count"] if rows else 0
        reports = [dict(row, date_basis="published" if row["has_publication_date"]
                        else "first_captured") for row in rows]
        # Editorial work is CPU-bound; keep the web event loop responsive.
        stories = await asyncio.to_thread(group_reports, reports, filters, as_of=end)
        non_current = sum(item.freshness_status != "current" for item in stories)
        if command.current_only:
            stories = [item for item in stories if item.freshness_status == "current"]
        matching = sum(item.report_count for item in stories)
        if command.full_stream:
            selected = stories[command.offset:command.offset + command.page_size]
            following = command.offset + len(selected)
            next_offset = following if following < len(stories) else None
        else:
            selected = await asyncio.to_thread(short_edition, stories, period=command.period,
                                              as_of=end, filters=filters)
            next_offset = None
        words = sum(item_words(item) for item in selected)
        return DigestEdition(
            period=command.period, window_start=start, window_end=end, generated_at=now,
            filters=filters, items=selected, word_count=words,
            estimated_read_seconds=math.ceil(words / 200 * 60),
            full_stream=command.full_stream, current_only=command.current_only, eligible_reports=eligible,
            scanned_reports=len(reports), matching_reports=matching, story_count=len(stories),
            excluded_non_reports=sum(not is_reporting_page(row) for row in reports),
            publisher_count=len({source.publisher_id
                                 for item in stories for source in item.sources}),
            sampled=eligible > len(reports), next_offset=next_offset,
            latest_capture_at=max((row["first_observed_at"] for row in rows), default=None),
            selected_publisher_count=len({source.publisher_id
                                         for item in selected for source in item.sources}),
            selected_days=len({item.published_at.date() for item in selected}),
            unavailable_summaries=sum(not item.summary_available for item in stories),
            excluded_stale_or_uncertain=non_current,
        )

    async def streams(self, user_id: UUID) -> list[SavedStream]:
        async with self._sessions() as session:
            user = await session.get(PlatformUserModel, user_id)
            if user is None:
                raise LookupError("Account not found")
            return _saved_streams(user.metadata_ or {})

    async def preferences(self, user_id: UUID) -> ReadingPreferences:
        async with self._sessions() as session:
            user = await session.get(PlatformUserModel, user_id)
            if user is None:
                raise LookupError("Account not found")
            metadata = user.metadata_ or {}
            prefs = ReadingPreferences.model_validate(metadata.get(PREFERENCES_KEY, {}))
            if prefs.stream_id:
                saved = next((s for s in _saved_streams(metadata) if s.id == prefs.stream_id), None)
                prefs = prefs.model_copy(update={"filters": saved.filters,
                                                "stream_id": saved.id}) if saved else ReadingPreferences()
            return prefs

    async def save_preferences(self, user_id: UUID, prefs: ReadingPreferences) -> ReadingPreferences:
        async with self._sessions() as session, session.begin():
            user = await session.get(PlatformUserModel, user_id, with_for_update=True)
            if user is None:
                raise LookupError("Account not found")
            metadata = dict(user.metadata_ or {})
            if prefs.stream_id:
                saved = next((s for s in _saved_streams(metadata) if s.id == prefs.stream_id), None)
                if saved is None:
                    raise LookupError("Feed not found")
                prefs = prefs.model_copy(update={"filters": saved.filters})
            metadata[PREFERENCES_KEY] = prefs.model_dump(mode="json")
            user.metadata_ = metadata
            user.updated_at = datetime.now(UTC)
            return prefs

    async def save_stream(self, user_id: UUID, command: StreamInput,
                          stream_id: UUID | None = None) -> SavedStream:
        async with self._sessions() as session, session.begin():
            user = await session.get(PlatformUserModel, user_id, with_for_update=True)
            if user is None:
                raise LookupError("Account not found")
            metadata = dict(user.metadata_ or {})
            streams = _saved_streams(metadata)
            previous = next((value for value in streams if value.id == stream_id), None)
            if stream_id and previous is None:
                raise LookupError("Stream not found")
            if previous is None and len(streams) >= 20:
                raise ValueError("You can save up to 20 streams. Delete one before adding another.")
            now = datetime.now(UTC)
            saved = SavedStream(**command.model_dump(), id=stream_id or uuid7(),
                                created_at=previous.created_at if previous else now, updated_at=now)
            metadata[STREAMS_KEY] = [value.model_dump(mode="json") for value in streams
                                    if value.id != saved.id] + [saved.model_dump(mode="json")]
            user.metadata_ = metadata
            user.updated_at = now
            return saved

    async def delete_stream(self, user_id: UUID, stream_id: UUID) -> None:
        async with self._sessions() as session, session.begin():
            user = await session.get(PlatformUserModel, user_id, with_for_update=True)
            if user is None:
                raise LookupError("Account not found")
            metadata = dict(user.metadata_ or {})
            streams = _saved_streams(metadata)
            remaining = [value.model_dump(mode="json") for value in streams
                         if value.id != stream_id]
            if len(remaining) == len(streams):
                raise LookupError("Stream not found")
            metadata[STREAMS_KEY] = remaining
            if metadata.get(PREFERENCES_KEY, {}).get("stream_id") == str(stream_id):
                metadata.pop(PREFERENCES_KEY, None)
            user.metadata_ = metadata
            user.updated_at = datetime.now(UTC)
