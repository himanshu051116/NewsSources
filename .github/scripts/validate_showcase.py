#!/usr/bin/env python3
"""Offline checks for the static Pages showcase. No external packages required."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "showcase"
FILES = ("index.html", "styles.css", "app.js", "favicon.svg", ".nojekyll")


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[tuple[str, str]] = []
        self.heading_count = 0
        self.tabs: list[dict[str, str]] = []
        self.panels: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if "id" in a:
            assert a["id"] not in self.ids, f"Duplicate HTML id: {a['id']}"
            self.ids.add(a["id"] or "")
        if tag == "h1":
            self.heading_count += 1
        if tag in {"a", "link", "script"}:
            key = "src" if tag == "script" else "href"
            if a.get(key):
                self.links.append((tag, a[key] or ""))
        if a.get("role") == "tab":
            self.tabs.append({k: v or "" for k, v in a.items()})
        if a.get("role") == "tabpanel":
            self.panels.append({k: v or "" for k, v in a.items()})


def check() -> None:
    for filename in FILES:
        assert (SITE / filename).is_file(), f"Missing site file: {filename}"
    html = (SITE / "index.html").read_text(encoding="utf-8")
    js = (SITE / "app.js").read_text(encoding="utf-8")
    css = (SITE / "styles.css").read_text(encoding="utf-8")
    p = SiteParser()
    p.feed(html)
    assert p.heading_count == 1, "Expected exactly one page-level h1"
    assert len(p.tabs) == len(p.panels) == 3, "Three workbench tabs required"
    assert "main" in p.ids and "record-list" in p.ids
    for tab in p.tabs:
        assert tab["aria-controls"] in p.ids
    for panel in p.panels:
        assert panel["aria-labelledby"] in p.ids
    assert "SYNTHETIC WORKBENCH" in html and "Fictional sources" in html
    assert "No live news" in html and "not a live backend connection" in html
    assert "COPYRIGHT" not in html.upper(), "Don't invent project licensing"
    for tag, link in p.links:
        if link.startswith("#"):
            assert link[1:] in p.ids, f"Broken on-page link {link}"
        elif link.startswith(("http://", "https://")):
            assert link.startswith("https://github.com/himanshu051116/NewsSources"), (
                f"Unexpected outbound URL: {link}"
            )
        else:
            assert (SITE / link).is_file(), f"Missing local asset {tag}: {link}"
    assert re.search(r"const RECORDS = Object\.freeze\(\[", js)
    assert js.count('id: "SRC-') == 4, "Demo should contain four fictional records"
    assert 'document.createElement' in js and '.textContent' in js, "Use safe DOM updates"
    assert not re.search(r"\b(fetch|XMLHttpRequest|WebSocket|localStorage)\s*\(", js), (
        "The static demo must not access live services or persist user input"
    )
    assert "@media(max-width:520px)" in css
    assert "prefers-reduced-motion" in css
    assert not re.search(r"https?://", css), "Styles should not load remote assets"
    print("PASS: local assets, navigation targets, tabs, demo labeling, basic privacy and responsiveness")


if __name__ == "__main__":
    check()
