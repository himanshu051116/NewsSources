"""Reader must expose PDF provenance while distinguishing OCR and tables from facts."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from newsintel.api.routes.article_intelligence_dashboard import article_intelligence_dashboard
from newsintel.domain.access import AccessRole, ROLE_PERMISSIONS


@pytest.mark.asyncio
async def test_article_reader_shows_pdf_review_container_and_explicit_uncertainty() -> None:
    role = AccessRole("viewer")
    auth = SimpleNamespace(
        role=SimpleNamespace(value="viewer"),
        permissions={item.value for item in ROLE_PERMISSIONS[role]},
    )
    html = await article_intelligence_dashboard(uuid4(), auth)
    assert 'id="pdfDocumentReview"' in html
    assert "PDF document review" in html
    assert "renderDocumentReview(v)" in html
    assert "document_table_candidates" in html
    assert "Tables requiring manual review" in html
    assert "not verified evidence" in html
    assert "OCR page(s) require checking" in html
    assert "Only part of the PDF was processed" in html
    assert "pdfClaimLink(c)" in html
    assert "Location only, not independent confirmation" in html
    assert "niSafeUrl(p.page_url" in html
    assert "niEsc(String(cell))" in html
    assert "rel=\"noopener noreferrer\"" in html


@pytest.mark.asyncio
async def test_embedded_reader_javascript_is_syntactically_valid(tmp_path) -> None:
    import re
    import shutil
    import subprocess

    if not shutil.which("node"):
        pytest.skip("Node.js is needed to parse browser JavaScript")
    role = AccessRole("viewer")
    auth = SimpleNamespace(
        role=SimpleNamespace(value="viewer"),
        permissions={item.value for item in ROLE_PERMISSIONS[role]},
    )
    html = await article_intelligence_dashboard(uuid4(), auth)
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.DOTALL)
    scripts = [value for value in blocks if "function renderDocumentReview" in value]
    assert len(scripts) == 1
    candidate = tmp_path / "article-reader.js"
    candidate.write_text(scripts[0], encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(candidate)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
