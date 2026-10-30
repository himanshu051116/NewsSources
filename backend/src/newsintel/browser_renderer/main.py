from __future__ import annotations

import asyncio
import hmac
import os
from hashlib import sha256
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from newsintel.adapters.http.safe_fetcher import validate_public_url

app = FastAPI(title="News Intelligence Browser Renderer", version="1")
_RENDER_TOKEN = os.getenv("NEWSINTEL_BROWSER_RENDERER_TOKEN", "")
_CONCURRENCY = max(1, min(4, int(os.getenv("NEWSINTEL_BROWSER_RENDERER_CONCURRENCY", "1"))))
_NAV_TIMEOUT_MS = max(2_000, min(45_000, int(os.getenv("NEWSINTEL_BROWSER_RENDERER_NAV_TIMEOUT_MS", "15000"))))
_SETTLE_MS = max(0, min(5_000, int(os.getenv("NEWSINTEL_BROWSER_RENDERER_SETTLE_MS", "1200"))))
_semaphore = asyncio.Semaphore(_CONCURRENCY)


class RenderRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4000)
    allowed_domains: list[str] = Field(min_length=1, max_length=20)
    max_html_bytes: int = Field(default=8_000_000, ge=10_000, le=12_000_000)

    @field_validator("allowed_domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            domain = value.strip().casefold().strip(".")
            if not domain or "://" in domain or "/" in domain or len(domain) > 253:
                raise ValueError("allowed_domains must contain host/domain names only")
            if domain not in seen:
                seen.add(domain)
                output.append(domain)
        return output


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/render")
async def render(
    request: RenderRequest,
    x_newsintel_renderer_token: str | None = Header(default=None),
) -> dict[str, object]:
    if len(_RENDER_TOKEN) < 32 or not x_newsintel_renderer_token or not hmac.compare_digest(
        _RENDER_TOKEN,
        x_newsintel_renderer_token,
    ):
        raise HTTPException(status_code=401, detail="invalid renderer token")

    allowed = tuple(request.allowed_domains)
    await validate_public_url(request.url, allowed_domains=allowed)

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - runtime packaging guard
        raise HTTPException(status_code=503, detail="playwright is not installed") from exc

    blocked = 0
    allowed_count = 0
    async with _semaphore, async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-extensions",
                "--disable-sync",
                "--no-first-run",
            ],
        )
        try:
            context = await browser.new_context(
                accept_downloads=False,
                service_workers="block",
                java_script_enabled=True,
            )
            page = await context.new_page()

            async def route_handler(route: object) -> None:
                nonlocal blocked, allowed_count
                req = route.request  # type: ignore[attr-defined]
                resource_type = str(req.resource_type)
                target = str(req.url)
                parsed = urlsplit(target)
                if resource_type in {"image", "media", "font"}:
                    blocked += 1
                    await route.abort()  # type: ignore[attr-defined]
                    return
                if parsed.scheme in {"data", "blob", "about"}:
                    allowed_count += 1
                    await route.continue_()  # type: ignore[attr-defined]
                    return
                try:
                    await validate_public_url(target, allowed_domains=allowed)
                except Exception:
                    blocked += 1
                    await route.abort()  # type: ignore[attr-defined]
                    return
                allowed_count += 1
                await route.continue_()  # type: ignore[attr-defined]

            await context.route("**/*", route_handler)
            response = await page.goto(
                request.url,
                wait_until="domcontentloaded",
                timeout=_NAV_TIMEOUT_MS,
            )
            if response is not None and response.status >= 400:
                raise HTTPException(status_code=502, detail=f"browser navigation HTTP {response.status}")
            if _SETTLE_MS:
                await page.wait_for_timeout(_SETTLE_MS)
            final_url = page.url
            await validate_public_url(final_url, allowed_domains=allowed)
            html = await page.content()
            encoded = html.encode("utf-8")
            if len(encoded) > request.max_html_bytes:
                raise HTTPException(status_code=413, detail="rendered HTML exceeded configured limit")
            return {
                "final_url": final_url,
                "html": html,
                "html_sha256": sha256(encoded).hexdigest(),
                "blocked_request_count": blocked,
                "allowed_request_count": allowed_count,
            }
        finally:
            await browser.close()


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8025, log_level="info")


if __name__ == "__main__":
    run()
