from datetime import UTC, datetime

import pytest

from newsintel.adapters.evidence.authority_search import (
    AuthorityAdapterType,
    AuthoritySearchExecutor,
    AuthoritySearchSpec,
    discover_candidate_urls,
    extract_document_text,
    render_search_url,
)
from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult


def _result(url: str, body: bytes, content_type: str = "text/html") -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": content_type},
        body=body,
        body_sha256="a" * 64,
        retrieved_at=datetime(2026, 8, 13, tzinfo=UTC),
        redirect_chain=(),
    )


def test_search_template_allows_only_query_placeholder() -> None:
    assert render_search_url("https://records.example/search?q={query}", "court order 42") == (
        "https://records.example/search?q=court+order+42"
    )
    with pytest.raises(ValueError):
        render_search_url("https://records.example/{path}?q={query}", "x")


def test_authority_spec_rejects_cross_domain_search_template() -> None:
    with pytest.raises(ValueError):
        AuthoritySearchSpec(
            authority_id="1",
            name="Court",
            evidence_class="court_record",
            base_url="https://court.example",
            allowed_domains=("court.example",),
            search_url_template="https://evil.example/search?q={query}",
        )


def test_search_link_discovery_filters_external_and_assets() -> None:
    result = _result(
        "https://court.example/search?q=x",
        b'''<html><body>
        <a href="/orders/123">Order</a>
        <a href="https://evil.example/copy">External</a>
        <a href="/static/logo.png">Logo</a>
        </body></html>''',
    )
    assert discover_candidate_urls(
        result,
        allowed_domains=("court.example",),
    ) == ["https://court.example/orders/123"]


def test_extract_document_text_removes_scripts() -> None:
    text = extract_document_text(
        b"<html><script>secret()</script><body><h1>Final Order</h1><p>The petition was dismissed.</p></body></html>",
        "text/html",
    )
    assert "Final Order" in text
    assert "petition was dismissed" in text
    assert "secret" not in text


class _FakeFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def fetch(self, request: FetchRequest) -> FetchResult:
        self.urls.append(request.url)
        if "/search" in request.url:
            return _result(
                request.url,
                b'<a href="/records/42">Record 42</a><a href="https://outside.example/no">No</a>',
            )
        return _result(
            request.url,
            b"<html><body>According to the official record, the project was approved in 2026.</body></html>",
        )


@pytest.mark.asyncio
async def test_executor_fetches_only_approved_authority_documents() -> None:
    fetcher = _FakeFetcher()
    executor = AuthoritySearchExecutor(fetcher)
    spec = AuthoritySearchSpec(
        authority_id="authority-1",
        name="Official Records",
        evidence_class="government_record",
        base_url="https://records.example",
        allowed_domains=("records.example",),
        search_url_template="https://records.example/search?q={query}",
        adapter_type=AuthorityAdapterType.GENERIC_HTML_SEARCH,
    )
    documents, attempts = await executor.retrieve(spec, query="project approved")
    assert len(documents) == 1
    assert documents[0].final_url == "https://records.example/records/42"
    assert all("outside.example" not in url for url in fetcher.urls)
    assert {item.status for item in attempts} >= {"search_fetched", "candidate_fetched"}


def test_search_template_rejects_embedded_secret_query_parameters() -> None:
    with pytest.raises(ValueError, match="API keys"):
        render_search_url(
            "https://records.example/search?api_key=secret-value&q={query}",
            "record",
        )

class _CkanFetcher:
    async def fetch(self, request: FetchRequest) -> FetchResult:
        if "package_search" in request.url:
            return _result(
                request.url,
                b'{"success":true,"result":{"results":[{"name":"inflation","resources":[{"url":"https://data.example.gov/records/inflation"}]}]}}',
                "application/json",
            )
        return _result(
            request.url,
            b"<html><body>Official inflation index for July 2026 was 123.4 points according to the statistical release.</body></html>",
        )


@pytest.mark.asyncio
async def test_executor_supports_ckan_package_search() -> None:
    executor = AuthoritySearchExecutor(_CkanFetcher())
    spec = AuthoritySearchSpec(
        authority_id="authority-ckan",
        name="Official Data",
        evidence_class="official_dataset",
        base_url="https://data.example.gov",
        allowed_domains=("data.example.gov",),
        search_url_template="https://data.example.gov/api/3/action/package_search?q={query}",
        adapter_type=AuthorityAdapterType.CKAN_PACKAGE_SEARCH,
    )
    documents, attempts = await executor.retrieve(spec, query="inflation", max_candidates=2)
    assert len(documents) >= 1
    assert any(item.final_url == "https://data.example.gov/records/inflation" for item in documents)
    assert any(item.status == "candidate_fetched" for item in attempts)


def test_generic_json_adapter_config_is_explicit() -> None:
    spec = AuthoritySearchSpec(
        authority_id="authority-json",
        name="Records API",
        evidence_class="government_record",
        base_url="https://records.example.gov",
        allowed_domains=("records.example.gov",),
        search_url_template="https://records.example.gov/api/search?q={query}",
        adapter_type=AuthorityAdapterType.GENERIC_JSON_SEARCH,
        adapter_config={"candidate_fields": ["document_url"]},
    )
    assert spec.adapter_config["candidate_fields"] == ["document_url"]


def test_generic_json_adapter_requires_candidate_fields() -> None:
    with pytest.raises(ValueError, match="candidate_fields"):
        AuthoritySearchSpec(
            authority_id="authority-json",
            name="Records API",
            evidence_class="government_record",
            base_url="https://records.example.gov",
            allowed_domains=("records.example.gov",),
            search_url_template="https://records.example.gov/api/search?q={query}",
            adapter_type=AuthorityAdapterType.GENERIC_JSON_SEARCH,
        )


def test_extract_document_text_supports_official_csv_evidence() -> None:
    text = extract_document_text(
        b"period,inflation_rate\n2026-07,7.2\n2026-08,6.9\n",
        "text/csv",
    )
    assert "2026-07" in text
    assert "7.2" in text
