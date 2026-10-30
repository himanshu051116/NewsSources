from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True, slots=True)
class RenderedPage:
    requested_url: str
    final_url: str
    html: bytes
    html_sha256: str
    blocked_request_count: int
    allowed_request_count: int


class BrowserRendererClient:
    """Client for the optional localhost-only browser-renderer sidecar.

    The main application never launches Chromium in-process. The sidecar is an
    explicit opt-in recovery path for publisher profiles that need JavaScript
    rendering after ordinary safe HTTP/hydration extraction is insufficient.
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 35.0,
        max_html_bytes: int = 8_000_000,
    ) -> None:
        _validate_loopback_base_url(base_url)
        if len(token) < 32:
            raise ValueError("browser renderer token must contain at least 32 characters")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._max_html_bytes = max_html_bytes

    async def render(
        self,
        *,
        url: str,
        allowed_domains: tuple[str, ...],
    ) -> RenderedPage:
        if not allowed_domains:
            raise ValueError("browser rendering requires an explicit domain allow-list")
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/render",
                headers={"X-NewsIntel-Renderer-Token": self._token},
                json={
                    "url": url,
                    "allowed_domains": list(allowed_domains),
                    "max_html_bytes": self._max_html_bytes,
                },
            )
            response.raise_for_status()
            payload = response.json()
        html_text = str(payload.get("html") or "")
        html = html_text.encode("utf-8")
        if not html or len(html) > self._max_html_bytes:
            raise ValueError("browser renderer returned an invalid HTML payload size")
        digest = sha256(html).hexdigest()
        advertised_digest = str(payload.get("html_sha256") or "")
        if advertised_digest and advertised_digest != digest:
            raise ValueError("browser renderer HTML digest mismatch")
        return RenderedPage(
            requested_url=url,
            final_url=str(payload.get("final_url") or url),
            html=html,
            html_sha256=digest,
            blocked_request_count=max(0, int(payload.get("blocked_request_count") or 0)),
            allowed_request_count=max(0, int(payload.get("allowed_request_count") or 0)),
        )


def _validate_loopback_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("browser renderer URL must be HTTP(S)")
    host = parsed.hostname.casefold()
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("browser renderer must be bound to localhost/loopback") from exc
    if not address.is_loopback:
        raise ValueError("browser renderer must be bound to localhost/loopback")
