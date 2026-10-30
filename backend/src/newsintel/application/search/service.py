from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, Integer, String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.articles.dto import IntelligenceSearchResultView, IntelligenceSearchView
from newsintel.core.ids import uuid7
from newsintel.domain.search.query_language import normalize_query, use_english_stemming
from newsintel.infrastructure.db.models import SearchQueryObservationModel


class InvalidSearchCursorError(ValueError):
    """Raised when a search cursor is malformed or belongs to another query/filter set."""


@dataclass(frozen=True, slots=True)
class SearchFilters:
    result_type: str = "all"
    language: str | None = None
    publisher: str | None = None
    lifecycle_status: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None

    def normalized(self, *, include_claims: bool, include_entities: bool = False) -> "SearchFilters":
        result_type = (self.result_type or "all").strip().lower()
        if result_type not in {"all", "event", "article", "claim", "entity"}:
            raise ValueError(f"unsupported result type: {result_type}")
        if result_type == "claim" and not include_claims:
            raise ValueError("claim search requires claim-view permission")
        if result_type == "entity" and not include_entities:
            raise ValueError("entity search requires analyst access")
        language = (self.language or "").strip().lower() or None
        publisher = (self.publisher or "").strip() or None
        lifecycle = (self.lifecycle_status or "").strip().lower() or None
        from_date = _as_utc(self.from_date)
        to_date = _as_utc(self.to_date)
        if from_date is not None and to_date is not None and from_date > to_date:
            raise ValueError("from_date must not be later than to_date")
        if result_type == "entity" and any((language, publisher, lifecycle, from_date, to_date)):
            raise ValueError("language, publisher, lifecycle, and date filters do not apply to entity-only search")
        return SearchFilters(
            result_type=result_type,
            language=language,
            publisher=publisher,
            lifecycle_status=lifecycle,
            from_date=from_date,
            to_date=to_date,
        )


_MATCHES_CTE = r"""
WITH search_input AS (
    SELECT
        websearch_to_tsquery('simple', :query) AS tsq,
        CASE WHEN :use_english_stemming THEN websearch_to_tsquery('english', :query) ELSE NULL::tsquery END AS tsq_en
),
event_matches AS (
    SELECT
        'event'::text AS result_type,
        e.id AS id,
        e.title AS title,
        concat(e.lifecycle_status, ' event · ', e.assignment_status, ' assignment') AS snippet,
        e.id AS event_id,
        NULL::uuid AS article_id,
        e.last_material_change_at AS occurred_at,
        round((greatest(
            ts_rank_cd(to_tsvector('simple', coalesce(e.title, '')), s.tsq),
            CASE WHEN :use_english_stemming THEN ts_rank_cd(
                to_tsvector('english', coalesce(e.title, '')), s.tsq_en
            ) ELSE 0 END
        ))::numeric, 8)::double precision AS score,
        jsonb_build_object(
            'lifecycle_status', e.lifecycle_status,
            'assignment_status', e.assignment_status
        ) AS metadata
    FROM events e
    CROSS JOIN search_input s
    WHERE :result_type IN ('all', 'event')
      AND e.created_at <= :snapshot_at
      AND (
          to_tsvector('simple', coalesce(e.title, '')) @@ s.tsq
          OR (
              :use_english_stemming
              AND to_tsvector('english', coalesce(e.title, '')) @@ s.tsq_en
          )
      )
      AND (:lifecycle_status IS NULL OR e.lifecycle_status = :lifecycle_status)
      AND (:from_date IS NULL OR e.last_material_change_at >= :from_date)
      AND (:to_date IS NULL OR e.last_material_change_at <= :to_date)
      AND (
          :language IS NULL OR EXISTS (
              SELECT 1 FROM articles ea
              WHERE ea.event_id = e.id AND lower(coalesce(ea.language, '')) = :language
          )
      )
      AND (
          :publisher_pattern IS NULL OR EXISTS (
              SELECT 1
              FROM articles epa
              JOIN publishers epp ON epp.id = epa.publisher_id
              WHERE epa.event_id = e.id
                AND (epp.name ILIKE :publisher_pattern ESCAPE E'\\' OR epp.slug ILIKE :publisher_pattern ESCAPE E'\\')
          )
      )
),
article_matches AS (
    SELECT
        'article'::text AS result_type,
        a.id AS id,
        coalesce(nullif(av.title, ''), a.title) AS title,
        CASE WHEN :use_english_stemming THEN ts_headline(
            'english',
            coalesce(av.text_content, ''),
            s.tsq_en,
            'MaxFragments=2, MaxWords=36, MinWords=12, StartSel=⟦, StopSel=⟧'
        ) ELSE ts_headline(
            'simple',
            coalesce(av.text_content, ''),
            s.tsq,
            'MaxFragments=2, MaxWords=36, MinWords=12, StartSel=⟦, StopSel=⟧'
        ) END AS snippet,
        a.event_id AS event_id,
        a.id AS article_id,
        coalesce(a.published_at, a.first_observed_at) AS occurred_at,
        round((greatest(
            ts_rank_cd(
                setweight(to_tsvector('simple', coalesce(av.title, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(av.byline, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(av.text_content, '')), 'C'),
                s.tsq
            ),
            CASE WHEN :use_english_stemming THEN ts_rank_cd(
                setweight(to_tsvector('english', coalesce(av.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(av.byline, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(av.text_content, '')), 'C'),
                s.tsq_en
            ) ELSE 0 END
        ))::numeric, 8)::double precision AS score,
        jsonb_build_object(
            'publisher', p.name,
            'publisher_slug', p.slug,
            'language', coalesce(a.language, av.language, ''),
            'canonical_url', a.canonical_url,
            'version_number', av.version_number
        ) AS metadata
    FROM article_versions av
    JOIN articles a ON a.id = av.article_id
    JOIN publishers p ON p.id = a.publisher_id
    JOIN events e ON e.id = a.event_id
    CROSS JOIN search_input s
    WHERE :result_type IN ('all', 'article')
      AND a.created_at <= :snapshot_at
      AND av.created_at <= :snapshot_at
      AND NOT EXISTS (
          SELECT 1 FROM article_versions newer
          WHERE newer.article_id = av.article_id
            AND newer.version_number > av.version_number
            AND newer.created_at <= :snapshot_at
      )
      AND (
          (
              setweight(to_tsvector('simple', coalesce(av.title, '')), 'A') ||
              setweight(to_tsvector('simple', coalesce(av.byline, '')), 'B') ||
              setweight(to_tsvector('simple', coalesce(av.text_content, '')), 'C')
          ) @@ s.tsq
          OR (
              :use_english_stemming AND (
                  setweight(to_tsvector('english', coalesce(av.title, '')), 'A') ||
                  setweight(to_tsvector('english', coalesce(av.byline, '')), 'B') ||
                  setweight(to_tsvector('english', coalesce(av.text_content, '')), 'C')
              ) @@ s.tsq_en
          )
      )
      AND (:language IS NULL OR lower(coalesce(a.language, av.language, '')) = :language)
      AND (:publisher_pattern IS NULL OR p.name ILIKE :publisher_pattern ESCAPE E'\\' OR p.slug ILIKE :publisher_pattern ESCAPE E'\\')
      AND (:lifecycle_status IS NULL OR e.lifecycle_status = :lifecycle_status)
      AND (:from_date IS NULL OR coalesce(a.published_at, a.first_observed_at) >= :from_date)
      AND (:to_date IS NULL OR coalesce(a.published_at, a.first_observed_at) <= :to_date)
),
claim_matches AS (
    SELECT
        'claim'::text AS result_type,
        c.id AS id,
        c.claim_text AS title,
        concat('Claim from ', a.title) AS snippet,
        a.event_id AS event_id,
        a.id AS article_id,
        c.created_at AS occurred_at,
        round((greatest(
            ts_rank_cd(to_tsvector('simple', coalesce(c.claim_text, '')), s.tsq),
            CASE WHEN :use_english_stemming THEN ts_rank_cd(
                to_tsvector('english', coalesce(c.claim_text, '')), s.tsq_en
            ) ELSE 0 END
        ))::numeric, 8)::double precision AS score,
        jsonb_build_object(
            'claim_type', coalesce(c.extraction_features ->> 'claim_type', ''),
            'verification_label', coalesce((
                SELECT cv.label FROM claim_verifications cv
                WHERE cv.claim_id = c.id
                ORDER BY cv.created_at DESC
                LIMIT 1
            ), ''),
            'publisher', p.name,
            'language', coalesce(a.language, av.language, '')
        ) AS metadata
    FROM article_claims c
    JOIN article_versions av ON av.id = c.article_version_id
    JOIN articles a ON a.id = c.article_id
    JOIN publishers p ON p.id = a.publisher_id
    JOIN events e ON e.id = a.event_id
    CROSS JOIN search_input s
    WHERE :include_claims = true
      AND :result_type IN ('all', 'claim')
      AND c.created_at <= :snapshot_at
      AND NOT EXISTS (
          SELECT 1 FROM article_versions newer
          WHERE newer.article_id = av.article_id
            AND newer.version_number > av.version_number
            AND newer.created_at <= :snapshot_at
      )
      AND (
          to_tsvector('simple', coalesce(c.claim_text, '')) @@ s.tsq
          OR (
              :use_english_stemming
              AND to_tsvector('english', coalesce(c.claim_text, '')) @@ s.tsq_en
          )
      )
      AND (:language IS NULL OR lower(coalesce(a.language, av.language, '')) = :language)
      AND (:publisher_pattern IS NULL OR p.name ILIKE :publisher_pattern ESCAPE E'\\' OR p.slug ILIKE :publisher_pattern ESCAPE E'\\')
      AND (:lifecycle_status IS NULL OR e.lifecycle_status = :lifecycle_status)
      AND (:from_date IS NULL OR c.created_at >= :from_date)
      AND (:to_date IS NULL OR c.created_at <= :to_date)
),
entity_matches AS (
    SELECT
        'entity'::text AS result_type,
        e.id AS id,
        e.canonical_name AS title,
        concat(e.entity_type, CASE WHEN e.country_code IS NOT NULL THEN concat(' · ', e.country_code) ELSE '' END) AS snippet,
        NULL::uuid AS event_id,
        NULL::uuid AS article_id,
        e.updated_at AS occurred_at,
        round((greatest(
            ts_rank_cd(to_tsvector('simple', coalesce(e.canonical_name, '')), s.tsq),
            coalesce((
                SELECT max(ts_rank_cd(to_tsvector('simple', coalesce(ea.alias, '')), s.tsq))
                FROM entity_aliases ea
                WHERE ea.entity_id = e.id
                  AND to_tsvector('simple', coalesce(ea.alias, '')) @@ s.tsq
            ), 0)
        ))::numeric, 8)::double precision AS score,
        jsonb_build_object(
            'entity_type', e.entity_type,
            'country_code', e.country_code,
            'matched_alias', (
                SELECT ea.alias
                FROM entity_aliases ea
                WHERE ea.entity_id = e.id
                  AND to_tsvector('simple', coalesce(ea.alias, '')) @@ s.tsq
                ORDER BY ts_rank_cd(to_tsvector('simple', coalesce(ea.alias, '')), s.tsq) DESC, ea.alias ASC
                LIMIT 1
            )
        ) AS metadata
    FROM canonical_entities e
    CROSS JOIN search_input s
    WHERE :include_entities = true
      AND :result_type IN ('all', 'entity')
      AND e.created_at <= :snapshot_at
      AND coalesce(e.resolution_status, 'active') = 'active'
      AND (
          to_tsvector('simple', coalesce(e.canonical_name, '')) @@ s.tsq
          OR EXISTS (
              SELECT 1 FROM entity_aliases ea
              WHERE ea.entity_id = e.id
                AND to_tsvector('simple', coalesce(ea.alias, '')) @@ s.tsq
          )
      )
      AND :language IS NULL
      AND :publisher_pattern IS NULL
      AND :lifecycle_status IS NULL
      AND :from_date IS NULL
      AND :to_date IS NULL
),
matches AS (
    SELECT * FROM event_matches
    UNION ALL
    SELECT * FROM article_matches
    UNION ALL
    SELECT * FROM claim_matches
    UNION ALL
    SELECT * FROM entity_matches
)
"""

_RESULTS_SQL = _MATCHES_CTE + r"""
SELECT result_type, id, title, snippet, event_id, article_id, occurred_at, score, metadata
FROM matches
WHERE (
    :cursor_score IS NULL
    OR score < :cursor_score
    OR (score = :cursor_score AND occurred_at < :cursor_occurred_at)
    OR (score = :cursor_score AND occurred_at = :cursor_occurred_at AND result_type > :cursor_result_type)
    OR (
        score = :cursor_score
        AND occurred_at = :cursor_occurred_at
        AND result_type = :cursor_result_type
        AND id::text > :cursor_id
    )
)
ORDER BY score DESC, occurred_at DESC, result_type ASC, id ASC
LIMIT :limit_plus_one
"""

_COUNTS_SQL = _MATCHES_CTE + r"""
SELECT result_type, count(*)::bigint AS result_count
FROM matches
GROUP BY result_type
"""

# asyncpg prepares queries before it sees parameter values. Optional filters
# and the first-page NULL cursor therefore need explicit SQL types.
_MATCH_BINDINGS = (
    bindparam("query", type_=String),
    bindparam("use_english_stemming", type_=Boolean),
    bindparam("result_type", type_=String),
    bindparam("snapshot_at", type_=DateTime(timezone=True)),
    bindparam("lifecycle_status", type_=String),
    bindparam("from_date", type_=DateTime(timezone=True)),
    bindparam("to_date", type_=DateTime(timezone=True)),
    bindparam("language", type_=String),
    bindparam("publisher_pattern", type_=String),
    bindparam("include_claims", type_=Boolean),
    bindparam("include_entities", type_=Boolean),
)
_RESULTS_QUERY = text(_RESULTS_SQL).bindparams(
    *_MATCH_BINDINGS,
    bindparam("cursor_score", type_=Float),
    bindparam("cursor_occurred_at", type_=DateTime(timezone=True)),
    bindparam("cursor_result_type", type_=String),
    bindparam("cursor_id", type_=String),
    bindparam("limit_plus_one", type_=Integer),
)
_COUNTS_QUERY = text(_COUNTS_SQL).bindparams(*_MATCH_BINDINGS)


class IntelligenceSearchService:
    """PostgreSQL FTS-backed corpus retrieval with snapshot-bound keyset pagination."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(
        self,
        *,
        query: str,
        limit: int = 30,
        include_claims: bool = False,
        include_entities: bool = False,
        filters: SearchFilters | None = None,
        cursor: str | None = None,
        record_telemetry: bool = True,
    ) -> IntelligenceSearchView:
        started = perf_counter()
        normalized = normalize_query(query)
        selected = (filters or SearchFilters()).normalized(include_claims=include_claims, include_entities=include_entities)
        if len(normalized) < 2:
            return IntelligenceSearchView(
                query=normalized,
                results=[],
                counts={},
                searched_claims=include_claims,
                searched_entities=include_entities,
                next_cursor=None,
                snapshot_at=None,
                search_mode="postgres_fts_v3_multilingual",
                filters=_filter_payload(selected),
            )

        fingerprint = _search_fingerprint(normalized, selected, include_claims, include_entities)
        cursor_data = _decode_cursor(cursor, expected_fingerprint=fingerprint) if cursor else None
        snapshot_at = cursor_data["snapshot_at"] if cursor_data else datetime.now(UTC)
        params = _query_params(
            normalized,
            selected,
            include_claims=include_claims,
            include_entities=include_entities,
            snapshot_at=snapshot_at,
            limit=limit,
            cursor_data=cursor_data,
        )

        async with self._session_factory() as session:
            row_result = await session.execute(_RESULTS_QUERY, params)
            rows = list(row_result.mappings().all())
            counts: dict[str, int] = {}
            if cursor_data is None:
                count_result = await session.execute(_COUNTS_QUERY, params)
                counts = {str(row.result_type): int(row.result_count) for row in count_result}

        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        results = [
            IntelligenceSearchResultView(
                result_type=str(row["result_type"]),
                id=row["id"],
                title=str(row["title"]),
                snippet=str(row["snippet"] or "") or None,
                event_id=row["event_id"],
                article_id=row["article_id"],
                occurred_at=row["occurred_at"],
                score=float(row["score"] or 0.0),
                metadata=_metadata_dict(row["metadata"]),
            )
            for row in visible_rows
        ]
        next_cursor = None
        if has_more and visible_rows:
            last = visible_rows[-1]
            next_cursor = _encode_cursor(
                fingerprint=fingerprint,
                snapshot_at=snapshot_at,
                score=float(last["score"] or 0.0),
                occurred_at=last["occurred_at"],
                result_type=str(last["result_type"]),
                item_id=last["id"],
            )
        response = IntelligenceSearchView(
            query=normalized,
            results=results,
            counts=counts,
            searched_claims=include_claims,
            searched_entities=include_entities,
            next_cursor=next_cursor,
            snapshot_at=snapshot_at,
            search_mode="postgres_fts_v3_multilingual",
            filters=_filter_payload(selected),
        )
        if record_telemetry:
            duration_ms = max(0.0, (perf_counter() - started) * 1000.0)
            await self._record_telemetry(
                fingerprint=fingerprint,
                filters=selected,
                include_claims=include_claims,
                duration_ms=duration_ms,
                result_count=sum(counts.values()) if counts else 0,
                returned_count=len(results),
                cursor_page=cursor_data is not None,
            )
        return response

    async def _record_telemetry(
        self,
        *,
        fingerprint: str,
        filters: SearchFilters,
        include_claims: bool,
        duration_ms: float,
        result_count: int,
        returned_count: int,
        cursor_page: bool,
    ) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                session.add(
                    SearchQueryObservationModel(
                        id=uuid7(),
                        query_fingerprint=fingerprint,
                        result_type=filters.result_type,
                        filters=_filter_payload(filters),
                        include_claims=include_claims,
                        duration_ms=duration_ms,
                        result_count=result_count,
                        returned_count=returned_count,
                        cursor_page=cursor_page,
                        created_at=datetime.now(UTC),
                    )
                )
        except Exception:
            # Telemetry is deliberately non-critical: retrieval must not fail because
            # an observability write is unavailable.
            return


def _query_params(
    query: str,
    filters: SearchFilters,
    *,
    include_claims: bool,
    include_entities: bool,
    snapshot_at: datetime,
    limit: int,
    cursor_data: dict[str, Any] | None,
) -> dict[str, object]:
    publisher_pattern = _literal_like_pattern(filters.publisher) if filters.publisher else None
    return {
        "query": query,
        "use_english_stemming": use_english_stemming(query, filters.language),
        "result_type": filters.result_type,
        "language": filters.language,
        "publisher_pattern": publisher_pattern,
        "lifecycle_status": filters.lifecycle_status,
        "from_date": filters.from_date,
        "to_date": filters.to_date,
        "include_claims": include_claims,
        "include_entities": include_entities,
        "snapshot_at": snapshot_at,
        "limit_plus_one": max(2, min(limit, 100) + 1),
        "cursor_score": cursor_data["score"] if cursor_data else None,
        "cursor_occurred_at": cursor_data["occurred_at"] if cursor_data else None,
        "cursor_result_type": cursor_data["result_type"] if cursor_data else None,
        "cursor_id": cursor_data["id"] if cursor_data else None,
    }


def _search_fingerprint(query: str, filters: SearchFilters, include_claims: bool, include_entities: bool = False) -> str:
    material = {
        "query": query,
        "filters": _filter_payload(filters),
        "include_claims": include_claims,
        "include_entities": include_entities,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _filter_payload(filters: SearchFilters) -> dict[str, object]:
    return {
        "result_type": filters.result_type,
        "language": filters.language,
        "publisher": filters.publisher,
        "lifecycle_status": filters.lifecycle_status,
        "from_date": filters.from_date.isoformat() if filters.from_date else None,
        "to_date": filters.to_date.isoformat() if filters.to_date else None,
    }


def _encode_cursor(
    *,
    fingerprint: str,
    snapshot_at: datetime,
    score: float,
    occurred_at: datetime,
    result_type: str,
    item_id: UUID,
) -> str:
    payload = {
        "v": 1,
        "f": fingerprint,
        "s": snapshot_at.astimezone(UTC).isoformat(),
        "r": round(score, 8),
        "t": occurred_at.astimezone(UTC).isoformat(),
        "k": result_type,
        "i": str(item_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, *, expected_fingerprint: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
        if payload.get("v") != 1 or payload.get("f") != expected_fingerprint:
            raise InvalidSearchCursorError("search cursor does not match the active query and filters")
        snapshot_at = datetime.fromisoformat(str(payload["s"]))
        occurred_at = datetime.fromisoformat(str(payload["t"]))
        if snapshot_at.tzinfo is None or occurred_at.tzinfo is None:
            raise ValueError("cursor timestamps must be timezone-aware")
        result_type = str(payload["k"])
        if result_type not in {"event", "article", "claim", "entity"}:
            raise ValueError("invalid result type")
        return {
            "snapshot_at": snapshot_at.astimezone(UTC),
            "score": float(payload["r"]),
            "occurred_at": occurred_at.astimezone(UTC),
            "result_type": result_type,
            "id": str(UUID(str(payload["i"]))),
        }
    except InvalidSearchCursorError:
        raise
    except Exception as exc:
        raise InvalidSearchCursorError("invalid search cursor") from exc


def _literal_like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _metadata_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}
