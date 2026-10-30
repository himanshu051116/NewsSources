"""S3-compatible raw HTML snapshots (including MinIO)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from hashlib import sha256
from uuid import UUID

import boto3
from botocore.exceptions import ClientError

from newsintel.adapters.artifacts.local_store import RawFetchArtifact


def _is_missing_object_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {})
    return isinstance(error, dict) and str(error.get("Code", "")) in {
        "404", "NoSuchKey", "NotFound",
    }


class S3RawArtifactStore:
    def __init__(
        self, *, endpoint_url: str, bucket: str, access_key: str,
        secret_key: str, prefix: str = "raw-html",
        server_side_encryption: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._sse = server_side_encryption
        self._client = boto3.client(
            "s3", endpoint_url=endpoint_url,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
        )

    async def save_raw_html(
        self, *, candidate_id: UUID, body: bytes, body_sha256: str,
        retrieved_at: datetime,
    ) -> RawFetchArtifact:
        return await self._save_raw(
            candidate_id=candidate_id, body=body, body_sha256=body_sha256,
            retrieved_at=retrieved_at, suffix=".html",
            content_type="text/html; charset=utf-8",
        )

    async def save_raw_pdf(
        self, *, candidate_id: UUID, body: bytes, body_sha256: str,
        retrieved_at: datetime,
    ) -> RawFetchArtifact:
        return await self._save_raw(
            candidate_id=candidate_id, body=body, body_sha256=body_sha256,
            retrieved_at=retrieved_at, suffix=".pdf",
            content_type="application/pdf",
        )

    async def _save_raw(
        self, *, candidate_id: UUID, body: bytes, body_sha256: str,
        retrieved_at: datetime, suffix: str, content_type: str,
    ) -> RawFetchArtifact:
        if len(body_sha256) != 64 or any(c not in "0123456789abcdef" for c in body_sha256):
            raise ValueError("body_sha256 must be a lowercase SHA-256 hex digest")
        if sha256(body).hexdigest() != body_sha256:
            raise ValueError("body_sha256 does not match raw artifact bytes")
        key_parts = [self._prefix, retrieved_at.strftime("%Y/%m/%d"),
                     str(candidate_id), f"{body_sha256}{suffix}"]
        key = "/".join(part for part in key_parts if part)
        await asyncio.to_thread(self._save, key, body, content_type)
        return RawFetchArtifact(
            artifact_uri=f"s3://{self._bucket}/{key}",
            sha256=body_sha256,
            byte_size=len(body),
            storage_backend="s3",
        )

    def _save(self, key: str, body: bytes, content_type: str) -> None:
        # Avoid HEAD -> PUT TOCTOU races: S3 If-None-Match is atomic on AWS and
        # supporting S3 implementations. Fail closed on unsupported endpoints.
        options: dict[str, object] = {
            "Bucket": self._bucket, "Key": key, "Body": body,
            "ContentType": content_type, "IfNoneMatch": "*",
        }
        if self._sse:
            options["ServerSideEncryption"] = self._sse
        try:
            self._client.put_object(**options)
            return
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"PreconditionFailed", "412", "ConditionalRequestConflict", "409"}:
                raise
        # A duplicate key must point to precisely the same bytes, even if a
        # caller supplied the same SHA-256 label. Never silently trust a HEAD.
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        try:
            stored = response["Body"].read(len(body) + 1)
        finally:
            response["Body"].close()
        if stored != body:
            raise FileExistsError(
                "raw S3 artifact key exists with different bytes; refusing overwrite"
            )
