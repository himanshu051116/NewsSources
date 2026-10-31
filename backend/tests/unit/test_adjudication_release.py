from pathlib import Path

from newsintel import __version__


def test_adjudication_release_contract():
    assert tuple(int(part) for part in __version__.split(".")) >= (1, 10, 0)
    root = Path(__file__).resolve().parents[3]
    migration = root / "backend" / "migrations" / "versions" / "0023_blind_adjudication_diagnostics.py"
    assert migration.exists()
    script = (root / "scripts" / "verification-benchmark.ps1").read_text(encoding="utf-8")
    assert '"sample"' in script
    assert '"review-sheet"' in script
    assert '"agreement"' in script
    assert '"finalize"' in script
    docs = (root / "docs" / "archive/implementation/v1.9-blind-adjudication.md").read_text(encoding="utf-8")
    assert "intentionally omits `predicted_label`" in docs
