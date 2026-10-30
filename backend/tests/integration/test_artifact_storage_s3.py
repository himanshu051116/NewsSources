"""Live S3-compatible persistence contract; run against an ephemeral LocalStack service."""
from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config

from newsintel.adapters.artifacts.s3_store import S3RawArtifactStore

ENDPOINT = os.environ.get("NEWSINTEL_TEST_S3_ENDPOINT")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not ENDPOINT, reason="S3 endpoint is not configured"),
]


def _client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )


@pytest.mark.asyncio
async def test_s3_round_trip_retains_original_raw_html() -> None:
    """A real put/head/get via a local S3 API, not a mocked boto3 invocation."""
    client = _client()
    bucket = f"newsintel-audit-{uuid4().hex[:16]}"
    client.create_bucket(Bucket=bucket)

    store = S3RawArtifactStore(
        endpoint_url=str(ENDPOINT), bucket=bucket,
        access_key="test", secret_key="test", prefix="raw-html",
    )
    candidate_id = uuid4()
    body = b"<html><body>First immutable snapshot</body></html>"
    digest = hashlib.sha256(body).hexdigest()
    time = datetime(2026, 10, 30, 12, tzinfo=UTC)

    first = await store.save_raw_html(
        candidate_id=candidate_id,
        body=body,
        body_sha256=digest,
        retrieved_at=time,
    )
    assert first.storage_backend == "s3"
    assert first.sha256 == digest
    assert first.byte_size == len(body)
    assert first.artifact_uri.startswith(f"s3://{bucket}/raw-html/2026/10/30/")
    key = first.artifact_uri.removeprefix(f"s3://{bucket}/")
    assert client.get_object(Bucket=bucket, Key=key)["Body"].read() == body

    # A second write using the same key is idempotent and must not overwrite
    # the original raw snapshot.
    repeated = await store.save_raw_html(
        candidate_id=candidate_id,
        body=b"mutated body that should not replace original",
        body_sha256=digest,
        retrieved_at=time,
    )
    assert repeated.artifact_uri == first.artifact_uri
    assert client.get_object(Bucket=bucket, Key=key)["Body"].read() == body


@pytest.mark.asyncio
async def test_s3_distinct_candidate_ids_preserve_both_snapshots() -> None:
    client = _client()
    bucket = f"newsintel-audit-{uuid4().hex[:16]}"
    client.create_bucket(Bucket=bucket)
    store = S3RawArtifactStore(
        endpoint_url=str(ENDPOINT), bucket=bucket,
        access_key="test", secret_key="test", prefix="raw-html",
    )
    body = b"same raw HTML, different discovery candidates"
    digest = hashlib.sha256(body).hexdigest()
    time = datetime(2026, 10, 30, 12, tzinfo=UTC)
    one = await store.save_raw_html(
        candidate_id=uuid4(), body=body, body_sha256=digest, retrieved_at=time,
    )
    two = await store.save_raw_html(
        candidate_id=uuid4(), body=body, body_sha256=digest, retrieved_at=time,
    )
    assert one.artifact_uri != two.artifact_uri
    assert client.get_object(
        Bucket=bucket, Key=one.artifact_uri.removeprefix(f"s3://{bucket}/")
    )["Body"].read() == body
    assert client.get_object(
        Bucket=bucket, Key=two.artifact_uri.removeprefix(f"s3://{bucket}/")
    )["Body"].read() == body
