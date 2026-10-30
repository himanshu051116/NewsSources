import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from newsintel.adapters.artifacts.local_store import LocalRawArtifactStore
from newsintel.core.ids import uuid7


@pytest.mark.asyncio
async def test_local_raw_artifact_store_writes_html_snapshot(tmp_path) -> None:
    store = LocalRawArtifactStore(tmp_path)
    body = b"<html><body><p>Article body</p></body></html>"
    body_sha256 = "a" * 64

    artifact = await store.save_raw_html(
        candidate_id=uuid7(),
        body=body,
        body_sha256=body_sha256,
        retrieved_at=datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
    )

    assert artifact.storage_backend == "local_filesystem"
    assert artifact.sha256 == body_sha256
    assert artifact.byte_size == len(body)
    assert artifact.artifact_uri.endswith(f"{body_sha256}.html")


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths")
async def test_raw_snapshot_supports_deep_windows_storage_paths(tmp_path) -> None:
    root = tmp_path / ("nested-" + "x" * 100)
    candidate_id = uuid7()
    retrieved_at = datetime(2026, 6, 29, tzinfo=UTC)
    artifact = await LocalRawArtifactStore(root).save_raw_html(
        candidate_id=candidate_id, body=b"snapshot", body_sha256="b" * 64,
        retrieved_at=retrieved_at,
    )
    target = root / "2026/06/29" / str(candidate_id) / ("b" * 64 + ".html")
    assert len(str(target)) > 260
    assert Path("\\\\?\\" + os.path.abspath(target)).read_bytes() == b"snapshot"
    assert artifact.byte_size == 8


@pytest.mark.asyncio
async def test_local_pdf_artifact_retains_original_pdf_bytes(tmp_path) -> None:
    body = b"%PDF-1.4\n%%EOF\n"
    digest = "c" * 64
    artifact = await LocalRawArtifactStore(tmp_path).save_raw_pdf(
        candidate_id=uuid7(),
        body=body,
        body_sha256=digest,
        retrieved_at=datetime(2026, 10, 30, tzinfo=UTC),
    )
    assert artifact.storage_backend == "local_filesystem"
    assert artifact.artifact_uri.endswith(f"{digest}.pdf")
    stored_path = Path(artifact.artifact_uri.removeprefix("file://"))
    assert stored_path.read_bytes() == body
