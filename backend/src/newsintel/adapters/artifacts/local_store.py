"""Immutable local raw HTML snapshots for the article worker."""
from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class RawFetchArtifact:
    artifact_uri: str
    storage_backend: str
    sha256: str
    byte_size: int

    def to_metadata(self) -> dict[str, str | int]:
        return asdict(self)


class LocalRawArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    async def save_raw_html(
        self, *, candidate_id: UUID, body: bytes, body_sha256: str,
        retrieved_at: datetime,
    ) -> RawFetchArtifact:
        return await self._save_raw(
            candidate_id=candidate_id, body=body, body_sha256=body_sha256,
            retrieved_at=retrieved_at, suffix=".html",
        )

    async def save_raw_pdf(
        self, *, candidate_id: UUID, body: bytes, body_sha256: str,
        retrieved_at: datetime,
    ) -> RawFetchArtifact:
        return await self._save_raw(
            candidate_id=candidate_id, body=body, body_sha256=body_sha256,
            retrieved_at=retrieved_at, suffix=".pdf",
        )

    async def _save_raw(
        self, *, candidate_id: UUID, body: bytes, body_sha256: str,
        retrieved_at: datetime, suffix: str,
    ) -> RawFetchArtifact:
        if len(body_sha256) != 64 or any(c not in "0123456789abcdef" for c in body_sha256):
            raise ValueError("body_sha256 must be a lowercase SHA-256 hex digest")
        destination = (
            self._root / retrieved_at.strftime("%Y/%m/%d")
            / str(candidate_id) / f"{body_sha256}{suffix}"
        )
        await asyncio.to_thread(_atomic_write, destination, body)
        return RawFetchArtifact(
            artifact_uri=destination.resolve().as_uri(),
            sha256=body_sha256,
            byte_size=len(body),
            storage_backend="local_filesystem",
        )


def _atomic_write(destination: Path, body: bytes) -> None:
    absolute = destination.absolute()
    filesystem_path = absolute
    if os.name == "nt":
        # Support long Windows paths even if MAX_PATH has not been disabled.
        filesystem_path = Path("\\\\?\\" + str(absolute))
    filesystem_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = filesystem_path.with_name(f".{filesystem_path.name}.{uuid4().hex}.tmp")
    try:
        tmp.write_bytes(body)
        os.replace(tmp, filesystem_path)
    finally:
        tmp.unlink(missing_ok=True)
