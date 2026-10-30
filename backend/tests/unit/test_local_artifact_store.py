import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from newsintel.adapters.artifacts.local_store import LocalRawArtifactStore
from newsintel.core.ids import uuid7


@pytest.mark.asyncio
async def test_local_raw_artifact_store_writes_html_snapshot(tmp_path) -> None:
    store = LocalRawArtifactStore(tmp_path)
    body = b"<html><body><p>Article body</p></body></html>"
    body_sha256 = sha256(body).hexdigest()

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
        candidate_id=candidate_id, body=b"snapshot", body_sha256=sha256(b"snapshot").hexdigest(),
        retrieved_at=retrieved_at,
    )
    target = root / "2026/06/29" / str(candidate_id) / (sha256(b"snapshot").hexdigest() + ".html")
    assert len(str(target)) > 260
    assert Path("\\\\?\\" + os.path.abspath(target)).read_bytes() == b"snapshot"
    assert artifact.byte_size == 8


@pytest.mark.asyncio
async def test_local_pdf_artifact_retains_original_pdf_bytes(tmp_path) -> None:
    body = b"%PDF-1.4\n%%EOF\n"
    digest = sha256(body).hexdigest()
    artifact = await LocalRawArtifactStore(tmp_path).save_raw_pdf(
        candidate_id=uuid7(),
        body=body,
        body_sha256=digest,
        retrieved_at=datetime(2026, 10, 30, tzinfo=UTC),
    )
    assert artifact.storage_backend == "local_filesystem"
    assert artifact.artifact_uri.endswith(f"{digest}.pdf")
    from urllib.parse import urlsplit
    from urllib.request import url2pathname

    stored_path = Path(url2pathname(urlsplit(artifact.artifact_uri).path))
    assert stored_path.read_bytes() == body


@pytest.mark.asyncio
async def test_local_pdf_snapshot_never_overwrites_existing_evidence(tmp_path) -> None:
    store = LocalRawArtifactStore(tmp_path)
    candidate_id = uuid7()
    time = datetime(2026, 10, 30, tzinfo=UTC)
    original = b"%PDF-original"
    digest = sha256(original).hexdigest()
    await store.save_raw_pdf(
        candidate_id=candidate_id, body=original,
        body_sha256=digest, retrieved_at=time,
    )
    with pytest.raises(ValueError, match="does not match"):
        await store.save_raw_pdf(
            candidate_id=candidate_id, body=b"%PDF-tampered",
            body_sha256=digest, retrieved_at=time,
        )
    saved = tmp_path / "2026/10/30" / str(candidate_id) / (digest + ".pdf")
    assert saved.read_bytes() == original
    # Simulate out-of-band corruption: an existing key must never be trusted.
    saved.write_bytes(b"%PDF-external-corruption")
    with pytest.raises(FileExistsError, match="different bytes"):
        await store.save_raw_pdf(
            candidate_id=candidate_id, body=original,
            body_sha256=digest, retrieved_at=time,
        )
