from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

VERIFICATION_MANIFEST_VERSION = "verification-manifest-v1"


@dataclass(frozen=True, slots=True)
class VerificationManifest:
    manifest_version: str
    manifest_sha256: str
    payload: dict[str, object]


def build_verification_manifest(payload: dict[str, object]) -> VerificationManifest:
    """Create a stable manifest hash for an immutable verification snapshot.

    The caller must exclude volatile fields such as ``created_at`` from ``payload``.
    Lists that are logically sets should be sorted by the caller so repeated builds
    from the same database state produce the same digest.
    """

    normalized = _json_safe(payload)
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return VerificationManifest(
        manifest_version=VERIFICATION_MANIFEST_VERSION,
        manifest_sha256=sha256(canonical).hexdigest(),
        payload=normalized,
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
