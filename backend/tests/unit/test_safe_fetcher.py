from unittest.mock import AsyncMock

import httpx
import pytest

from newsintel.adapters.http.safe_fetcher import (
    FetchRequest,
    SafeHttpFetcher,
    UnsafeTargetError,
    _validate_url,
)


@pytest.mark.asyncio
async def test_conditional_304_is_not_a_redirect(monkeypatch):
    real_client = httpx.AsyncClient
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(304, headers={"ETag": '"same"'})

    monkeypatch.setattr("newsintel.adapters.http.safe_fetcher.validate_public_url", AsyncMock())
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(respond),
    ))
    result = await SafeHttpFetcher(user_agent="Regression test").fetch(
        FetchRequest(url="https://news.example/feed", etag='"same"'),
    )
    assert result.not_modified
    assert result.body == b""
    assert result.redirect_chain == ()
    assert len(calls) == 1
    assert calls[0].headers["If-None-Match"] == '"same"'


@pytest.mark.asyncio
async def test_real_redirect_still_validates_destination(monkeypatch):
    real_client = httpx.AsyncClient
    validate = AsyncMock()

    def respond(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"Location": "/feed"})
        return httpx.Response(200, content=b"news")

    monkeypatch.setattr("newsintel.adapters.http.safe_fetcher.validate_public_url", validate)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(respond),
    ))
    result = await SafeHttpFetcher(user_agent="Regression test").fetch(
        FetchRequest(url="https://news.example/old"),
    )
    assert result.final_url == "https://news.example/feed"
    assert result.redirect_chain == ("https://news.example/old",)
    assert validate.await_count == 2


@pytest.mark.asyncio
async def test_rejects_localhost_to_prevent_ssrf() -> None:
    with pytest.raises(UnsafeTargetError, match="non-public"):
        await _validate_url("http://127.0.0.1/private")


@pytest.mark.asyncio
async def test_rejects_non_http_scheme() -> None:
    with pytest.raises(UnsafeTargetError, match="only public HTTP"):
        await _validate_url("file:///etc/passwd")



@pytest.mark.asyncio
async def test_request_domain_allowlist_rejects_cross_domain_before_network_resolution() -> None:
    with pytest.raises(UnsafeTargetError, match="domain allow-list"):
        await _validate_url(
            "https://outside.example/redirected",
            allowed_domains=("records.example",),
        )
