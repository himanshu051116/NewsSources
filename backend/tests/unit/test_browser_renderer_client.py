import pytest

from newsintel.adapters.rendering.browser_client import BrowserRendererClient


def test_browser_renderer_client_requires_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="localhost/loopback"):
        BrowserRendererClient(base_url="https://renderer.example.com", token="x" * 32)


def test_browser_renderer_client_requires_long_token() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        BrowserRendererClient(base_url="http://127.0.0.1:8025", token="short")
