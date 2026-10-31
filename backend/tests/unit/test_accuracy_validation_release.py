from pathlib import Path

from newsintel import __version__
from newsintel.domain.intelligence.validation_program import VALIDATION_PROGRAM_VERSION


def test_accuracy_validation_release_contract() -> None:
    root = Path(__file__).resolve().parents[3]
    assert tuple(int(part) for part in __version__.split(".")) >= (1, 10, 0)
    assert VALIDATION_PROGRAM_VERSION == "accuracy-validation-program-v1"
    route = (root / "backend/src/newsintel/api/routes/intelligence.py").read_text(encoding="utf-8")
    page = (root / "backend/src/newsintel/api/routes/accuracy_dashboard.py").read_text(encoding="utf-8")
    docs = (root / "docs/archive/implementation/v1.10-validation-program.md").read_text(encoding="utf-8")
    assert "/verification-benchmark/{benchmark_set}/validation-report" in route
    assert "Golden-corpus validation" in page
    assert "Wilson" in docs
