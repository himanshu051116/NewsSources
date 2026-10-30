from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx


class SemanticAdapterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticSearchHit:
    point_id: str
    score: float
    payload: dict[str, object]


class OllamaEmbeddingClient:
    """Small Ollama embedding adapter with no paid/network fallback."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 20.0,
        expected_dimension: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self.model = model
        self._timeout = timeout_seconds
        self._expected_dimension = expected_dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        normalized = [text.strip()[:12_000] for text in texts if text.strip()]
        if not normalized:
            return []
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            modern = await client.post(
                urljoin(self._base_url, "api/embed"),
                json={"model": self.model, "input": normalized},
            )
            if 200 <= modern.status_code < 300:
                payload = modern.json()
                embeddings = payload.get("embeddings")
                if isinstance(embeddings, list):
                    return self._validate_vectors(embeddings, expected_count=len(normalized))
            vectors: list[list[float]] = []
            for text in normalized:
                legacy = await client.post(
                    urljoin(self._base_url, "api/embeddings"),
                    json={"model": self.model, "prompt": text},
                )
                if legacy.status_code < 200 or legacy.status_code >= 300:
                    raise SemanticAdapterError(
                        f"local embedding server returned HTTP {legacy.status_code}"
                    )
                payload = legacy.json()
                vector = payload.get("embedding")
                vectors.extend(self._validate_vectors([vector], expected_count=1))
            return vectors

    def _validate_vectors(
        self,
        values: list[Any],
        *,
        expected_count: int,
    ) -> list[list[float]]:
        if len(values) != expected_count:
            raise SemanticAdapterError(
                f"embedding count mismatch: expected {expected_count}, got {len(values)}"
            )
        output: list[list[float]] = []
        for raw in values:
            if not isinstance(raw, list) or not raw:
                raise SemanticAdapterError("embedding response did not contain a vector")
            try:
                vector = [float(value) for value in raw]
            except (TypeError, ValueError) as exc:
                raise SemanticAdapterError("embedding vector contained non-numeric values") from exc
            if self._expected_dimension and len(vector) != self._expected_dimension:
                raise SemanticAdapterError(
                    "embedding dimension mismatch: "
                    f"expected {self._expected_dimension}, got {len(vector)}"
                )
            output.append(vector)
        return output


class QdrantSemanticIndex:
    """REST-based Qdrant adapter so the Python client is not required."""

    def __init__(
        self,
        *,
        base_url: str,
        collection: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self.collection = collection
        self._timeout = timeout_seconds
        self._ensured_dimension: int | None = None

    async def ensure_collection(self, dimension: int) -> None:
        if self._ensured_dimension == dimension:
            return
        url = urljoin(self._base_url, f"collections/{self.collection}")
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            response = await client.get(url)
            if response.status_code == 404:
                created = await client.put(
                    url,
                    json={"vectors": {"size": dimension, "distance": "Cosine"}},
                )
                if created.status_code < 200 or created.status_code >= 300:
                    raise SemanticAdapterError(
                        f"Qdrant collection creation failed HTTP {created.status_code}"
                    )
            elif response.status_code < 200 or response.status_code >= 300:
                raise SemanticAdapterError(
                    f"Qdrant collection check failed HTTP {response.status_code}"
                )
            else:
                payload = response.json()
                configured = _qdrant_vector_size(payload)
                if configured is not None and configured != dimension:
                    raise SemanticAdapterError(
                        f"Qdrant vector size mismatch: collection={configured}, embedding={dimension}"
                    )
        self._ensured_dimension = dimension

    async def require_collection(self, dimension: int) -> None:
        if self._ensured_dimension == dimension:
            return
        url = urljoin(self._base_url, f"collections/{self.collection}")
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            response = await client.get(url)
        if response.status_code == 404:
            raise SemanticAdapterError(
                f"Qdrant collection {self.collection!r} does not exist; backfill semantic article versions before running reranking experiments"
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise SemanticAdapterError(
                f"Qdrant collection check failed HTTP {response.status_code}"
            )
        payload = response.json()
        configured = _qdrant_vector_size(payload)
        if configured is not None and configured != dimension:
            raise SemanticAdapterError(
                f"Qdrant vector size mismatch: collection={configured}, embedding={dimension}"
            )
        self._ensured_dimension = dimension

    async def upsert(self, points: list[dict[str, object]]) -> None:
        if not points:
            return
        url = urljoin(
            self._base_url,
            f"collections/{self.collection}/points?wait=true",
        )
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            response = await client.put(url, json={"points": points})
        if response.status_code < 200 or response.status_code >= 300:
            raise SemanticAdapterError(f"Qdrant upsert failed HTTP {response.status_code}")

    async def search(
        self,
        *,
        vector: list[float],
        limit: int,
        cutoff_epoch: float,
        exclude_point_id: str | None = None,
        create_if_missing: bool = True,
    ) -> list[SemanticSearchHit]:
        if create_if_missing:
            await self.ensure_collection(len(vector))
        else:
            await self.require_collection(len(vector))
        conditions: dict[str, object] = {
            "must": [
                {
                    "key": "observed_at_epoch",
                    "range": {"lt": cutoff_epoch},
                }
            ]
        }
        if exclude_point_id:
            conditions["must_not"] = [{"has_id": [exclude_point_id]}]
        query_url = urljoin(
            self._base_url,
            f"collections/{self.collection}/points/query",
        )
        query_payload = {
            "query": vector,
            "filter": conditions,
            "limit": max(1, min(limit, 100)),
            "with_payload": True,
        }
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            response = await client.post(query_url, json=query_payload)
            if response.status_code == 404:
                legacy_url = urljoin(
                    self._base_url,
                    f"collections/{self.collection}/points/search",
                )
                response = await client.post(
                    legacy_url,
                    json={
                        "vector": vector,
                        "filter": conditions,
                        "limit": max(1, min(limit, 100)),
                        "with_payload": True,
                    },
                )
        if response.status_code < 200 or response.status_code >= 300:
            raise SemanticAdapterError(f"Qdrant search failed HTTP {response.status_code}")
        data = response.json().get("result")
        if isinstance(data, dict):
            raw_hits = data.get("points", [])
        else:
            raw_hits = data if isinstance(data, list) else []
        hits: list[SemanticSearchHit] = []
        for item in raw_hits:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload")
            hits.append(
                SemanticSearchHit(
                    point_id=str(item.get("id") or ""),
                    score=max(0.0, min(1.0, float(item.get("score") or 0.0))),
                    payload=dict(payload) if isinstance(payload, dict) else {},
                )
            )
        return hits


def _qdrant_vector_size(payload: dict[str, Any]) -> int | None:
    try:
        vectors = payload["result"]["config"]["params"]["vectors"]
        if isinstance(vectors, dict) and "size" in vectors:
            return int(vectors["size"])
    except (KeyError, TypeError, ValueError):
        return None
    return None
