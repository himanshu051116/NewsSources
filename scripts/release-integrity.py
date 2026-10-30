#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "0033_grounded_news_explainer"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check release-tree integrity without network access.")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args()

    checks: dict[str, object] = {}
    failures: list[str] = []

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = str(pyproject["project"]["version"])
    init_text = (ROOT / "backend/src/newsintel/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_text)
    package_version = match.group(1) if match else None
    checks["project_version"] = project_version
    checks["package_version"] = package_version
    if package_version != project_version:
        failures.append("pyproject and package versions do not match")

    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8") if (ROOT / "uv.lock").exists() else ""
    lock_match = re.search(
        r'\[\[package\]\]\s+name = "news-intelligence-platform"\s+version = "([^"]+)"\s+source = \{ editable = "\." \}',
        lock_text,
        re.MULTILINE,
    )
    lock_project_version = lock_match.group(1) if lock_match else None
    checks["lock_project_version"] = lock_project_version
    if lock_project_version != project_version:
        failures.append("uv.lock editable project version does not match pyproject")

    schema_text = (ROOT / "backend/src/newsintel/core/schema.py").read_text(encoding="utf-8")
    schema_match = re.search(r'EXPECTED_SCHEMA_REVISION\s*=\s*["\']([^"\']+)["\']', schema_text)
    schema_revision = schema_match.group(1) if schema_match else None
    checks["expected_schema_revision"] = schema_revision
    if schema_revision != EXPECTED_HEAD:
        failures.append(f"schema expected head is not {EXPECTED_HEAD}")

    migration = ROOT / f"backend/migrations/versions/{EXPECTED_HEAD}.py"
    checks["expected_migration_exists"] = migration.is_file()
    if not migration.is_file():
        failures.append(f"expected migration is missing: {EXPECTED_HEAD}")

    # CI creates __pycache__ during compileall and pytest; only committed artifacts
    # are release integrity defects, not generated files in the test workspace.
    try:
        tracked_raw = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT, stderr=subprocess.DEVNULL,
        )
        tracked_paths = [Path(item.decode("utf-8", errors="replace"))
                         for item in tracked_raw.split(b"\0") if item]
    except (OSError, subprocess.CalledProcessError):
        failures.append("cannot inspect tracked release files (git ls-files failed)")
        tracked_paths = []
    forbidden = []
    for rel in tracked_paths:
        if any(part in {"__pycache__", ".pytest_cache"} for part in rel.parts):
            forbidden.append(str(rel))
        elif rel.suffix == ".pyc" or rel.name in {"structlog.py", "asyncpg.py"}:
            forbidden.append(str(rel))
    checks["forbidden_artifacts"] = sorted(set(forbidden))
    if forbidden:
        failures.append("tracked release contains caches, bytecode, or dependency shims")
    required_python_modules = [
        "backend/src/newsintel/adapters/artifacts/local_store.py",
        "backend/src/newsintel/adapters/artifacts/s3_store.py",
    ]
    missing_python_modules = [path for path in required_python_modules
                              if not (ROOT / path).is_file()]
    checks["missing_python_modules"] = missing_python_modules
    if missing_python_modules:
        failures.append("required artifact storage adapters are missing")

    populated_secrets: list[str] = []
    for env_path in (ROOT / ".env.example", ROOT / ".env.production.example"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            sensitive = key.endswith(("_API_KEY", "_SECRET", "_PASSWORD"))
            placeholder = (not value) or value.casefold() in {"change-me", "example", "placeholder"} or value.startswith("CHANGE_ME")
            if sensitive and not placeholder:
                populated_secrets.append(f"{env_path.name}:{key}")

    required_release_assets = (
        "Dockerfile",
        "compose.production.yaml",
        ".env.production.example",
        "PRODUCTION-RUNBOOK.md",
        "deploy/Caddyfile",
        ".github/workflows/ci.yml",
        "scripts/production-smoke.sh",
        "scripts/production-acceptance.sh",
        "scripts/production-backup.sh",
        "scripts/production-restore.sh",
    )
    missing_assets = [name for name in required_release_assets if not (ROOT / name).is_file()]
    checks["missing_production_assets"] = missing_assets
    if missing_assets:
        failures.append("required production deployment assets are missing")
    checks["populated_example_secrets"] = populated_secrets
    if populated_secrets:
        failures.append(".env.example contains populated secret-like values")

    checks["failure_count"] = len(failures)
    report = {"ok": not failures, "checks": checks, "failures": failures}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("release-integrity:", "PASS" if not failures else "FAIL")
        for failure in failures:
            print(f"- {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
