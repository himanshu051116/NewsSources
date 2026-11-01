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
    assert len(p.tabs) == len(p.panels) == 6, "Six workbench tabs required"
    assert "main" in p.ids and "record-list" in p.ids
    for tab in p.tabs:
        assert tab["aria-controls"] in p.ids
    for panel in p.panels:
        assert panel["aria-labelledby"] in p.ids
    assert "SYNTHETIC WORKBENCH" in html and "Fictional sources" in html
    assert "No live news" in html and "not a live backend connection" in html
    assert 'Content-Security-Policy' in html
    assert "connect-src 'none'" in html
    assert "https://himanshu051116.github.io/NewsSources/" in html
    assert 'data-filter="derived"' in html, "Derived reports must have an explicit filter"
    assert len(re.findall(r'data-jump="SRC-\d{3}"', html)) == 3
    assert len(re.findall(r'data-lineage-record="SRC-\d{3}"', html)) == 4
    assert 'id="lineage-open-record"' in html
    assert 'id="demo-timeline"' in html
    assert all(name in p.ids for name in ("timeline-detail-kind", "timeline-detail-index",
        "timeline-detail-title", "timeline-detail-date", "timeline-detail-note",
        "timeline-detail-lineage", "timeline-prev", "timeline-next", "timeline-open"))
    assert 'id="timeline-prev" aria-label="Previous timeline record" disabled' in html
    assert 'v 0.7' in html, "Version marker must match the current exhibit"
    assert all(name in p.ids for name in ("lineage-detail-kind", "lineage-detail-id",
                                         "lineage-detail-title", "lineage-detail-note"))
    assert 'id="reset-workbench"' in html
    assert 'id="comparison-panel"' in html
    assert 'id="tab-audit"' in html and 'id="panel-audit"' in html
    assert 'id="tab-coverage"' in html and 'id="panel-coverage"' in html
    assert 'id="tab-review"' in html and 'id="panel-review"' in html
    assert 'id="audit-open-review"' in html
    assert len(re.findall(r'data-review-claim="CLM-\d{2}"', html)) == 3
    assert all(name in p.ids for name in ("review-claim-title", "review-status", "review-note",
        "review-note-count", "review-clear-note", "review-notes-count", "review-followups-count",
        "review-open-primary", "review-open-related", "review-open-lineage", "review-note-warning"))
    assert 'maxlength="600"' in html
    assert "SESSION ONLY" in html and "NOT INDEPENDENTLY VERIFIED" in html
    assert all(name in p.ids for name in ("coverage-left", "coverage-right", "coverage-swap",
        "coverage-left-excerpt", "coverage-right-excerpt", "coverage-relationship",
        "coverage-interpretation", "coverage-open-left", "coverage-open-right", "coverage-class"))
    assert html.count('<option value="SRC-') == 8, "Four source choices in each comparison selector"
    assert 'id="audit-original"' in html and 'id="audit-related"' in html
    assert len(re.findall(r'data-claim="CLM-\d{2}"', html)) == 3, "Three selectable audit claims required"
    assert 'case-briefing' in html, "Case briefing should be visible to all visitors"
    assert 'id="limits"' in html
    assert "COPYRIGHT" not in html.upper(), "Don't invent project licensing"
    for tag, link in p.links:
        if link.startswith("#"):
            assert link[1:] in p.ids, f"Broken on-page link {link}"
        elif link.startswith(("http://", "https://")):
            assert (
                link.startswith("https://github.com/himanshu051116/NewsSources")
                or link == "https://himanshu051116.github.io/NewsSources/"
            ), f"Unexpected outbound URL: {link}"
        else:
            assert (SITE / link).is_file(), f"Missing local asset {tag}: {link}"
    assert re.search(r"const RECORDS = Object\.freeze\(\[", js)
    assert js.count('id: "SRC-') == 4, "Demo should contain four fictional records"
    assert js.count('id: "CLM-') == 3, "Demo claim register should contain three claims"
    for feature in ("renderClaim", "audit-original", "audit-related", "audit-status",
                    "data-claim", '"audit"', 'CLAIMS.find'):
        assert feature in js, f"Missing claim audit behavior: {feature}"
    assert '"240"' in js and '"215"' in js, "Known fictional revision must be highlighted"
    for feature in ("renderReview", "reviewEntries", "REVIEW_SOURCE_IDS",
                    "activeReviewEntry", "review-clear-note", "audit-open-review",
                    "renderCoverage", "coverage-left", "coverage-right", "coverage-swap",
                    "coverage-open-left", "coverage-open-right",
                    "data-lineage-record", "renderLineageInspector", "lineage-open-record",
                    "data-jump", "timeline-select", "renderTimelineInspector",
                    "chooseTimelineRecord", "timeline-prev", "timeline-next", "timeline-open",
                    "selectRecord", "reset-workbench", "renderMarkedExcerpt"):
        assert feature in js, f"Missing interactive case behavior: {feature}"
    lineage_all = '$$' + '("[data-lineage-record]").forEach'
    assert js.count(lineage_all) == 2, "Inspector and node listeners must use collection selectors"
    claim_all = '$$' + '("[data-claim]").forEach'
    assert js.count(claim_all) == 2, "Audit card listeners and rendering must use collection selectors"
    assert not re.search(r'(?<![$])[$][(][^)]*[)][.]forEach[(]', js), (
        "querySelector returns one element; forEach requires querySelectorAll"
    )
    filter_all = '$$' + '("[data-filter]").forEach'
    filter_one = '$' + '("[data-filter]").forEach'
    assert js.count(filter_all) == 4, "All four filter operations must use collection selectors"
    assert filter_one not in js.replace(filter_all, ''), "Singular filter selection breaks reset"
    review_all = '$$' + '("[data-review-claim]").forEach'
    assert js.count(review_all) == 2, "Review queue and selection must iterate collections"
    assert not any(term in js for term in ("sessionStorage", "indexedDB", "document.cookie")), (
        "Reviewer draft state must stay in memory and disappear on reload"
    )
    assert "innerHTML" not in js, "Do not inject user-controlled HTML"
    assert 'document.createElement' in js and '.textContent' in js, "Use safe DOM updates"
    assert not re.search(r"\b(fetch|XMLHttpRequest|WebSocket|localStorage)\s*\(", js), (
        "The static demo must not access live services or persist user input"
    )
    assert "@media(max-width:520px)" in css
    assert "prefers-reduced-motion" in css
    for selector in (".review-grid", ".review-queue__claim", ".review-detail",
                     ".review-session-flag", ".review-privacy"):
        assert selector in css, f"Missing reviewer workspace styling: {selector}"
    for selector in (".coverage-controls", ".coverage-columns", ".coverage-finding", ".coverage-document"):
        assert selector in css, f"Missing coverage comparison styling: {selector}"
    for selector in (".chronology__inspector", ".chronology__event", ".chronology__actions"):
        assert selector in css, f"Missing timeline styling: {selector}"
    assert not re.search(r"https?://", css), "Styles should not load remote assets"
    print("PASS: assets, six tabs, evidence navigation, temporary review notes, privacy, selectors and responsive CSS")


if __name__ == "__main__":
    check()
