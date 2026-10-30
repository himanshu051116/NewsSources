from datetime import UTC, datetime
from hashlib import sha256

import pytest

from newsintel.adapters.entities.registry import (
    search_configured_registry,
    validate_registry_search_template,
)
from newsintel.adapters.http.safe_fetcher import FetchResult


class FakeFetcher:
    def __init__(self, body: bytes):
        self.body = body
        self.request = None

    async def fetch(self, request):
        self.request = request
        return FetchResult(
            requested_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "application/json"},
            body=self.body,
            body_sha256=sha256(self.body).hexdigest(),
            retrieved_at=datetime.now(UTC),
            redirect_chain=(),
        )


@pytest.mark.asyncio
async def test_configured_registry_search_is_domain_scoped_and_parses_fields():
    body = b'{"results":[{"qid":"Q123","name":"Reserve Bank of India","kind":"organization","country":"IN","aliases":["RBI"]}]}'
    fetcher = FakeFetcher(body)
    result = await search_configured_registry(
        fetcher,
        base_url="https://registry.example.gov",
        search_url_template="https://registry.example.gov/api/search?q={query}",
        query="Reserve Bank of India",
        config={
            "results_path": "results",
            "id_field": "qid",
            "label_field": "name",
            "type_field": "kind",
            "country_field": "country",
            "aliases_field": "aliases",
        },
    )
    assert result.candidates[0].external_id == "Q123"
    assert fetcher.request.allowed_domains == ("registry.example.gov",)


def test_registry_template_rejects_cross_domain_and_embedded_secret():
    with pytest.raises(ValueError):
        validate_registry_search_template(
            "https://registry.example.gov",
            "https://evil.example/search?q={query}",
        )
    with pytest.raises(ValueError):
        validate_registry_search_template(
            "https://registry.example.gov",
            "https://registry.example.gov/search?q={query}&api_key=secret",
        )
