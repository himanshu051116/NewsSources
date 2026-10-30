from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

LINEAGE_FINGERPRINT_VERSION = "content-lineage-minhash-v1"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.I)


@dataclass(frozen=True, slots=True)
class ContentLineageFingerprint:
    exact_signature: str
    minhash: tuple[int, ...]
    token_count: int
    shingle_count: int
    version: str = LINEAGE_FINGERPRINT_VERSION


def fingerprint_content(
    text: str,
    *,
    shingle_size: int = 5,
    minhash_size: int = 24,
    max_tokens: int = 4_000,
) -> ContentLineageFingerprint:
    tokens = tuple(token.lower() for token in _TOKEN_PATTERN.findall(text))[:max_tokens]
    exact_signature = sha256(" ".join(tokens).encode("utf-8")).hexdigest()
    if len(tokens) < shingle_size:
        shingles = {" ".join(tokens)} if tokens else set()
    else:
        shingles = {
            " ".join(tokens[index : index + shingle_size])
            for index in range(len(tokens) - shingle_size + 1)
        }
    minhash: tuple[int, ...]
    if shingles:
        minhash = tuple(
            min(
                int.from_bytes(
                    sha256(f"{seed}:{shingle}".encode("utf-8")).digest()[:8],
                    "big",
                )
                for shingle in shingles
            )
            for seed in range(minhash_size)
        )
    else:
        minhash = ()
    return ContentLineageFingerprint(
        exact_signature=exact_signature,
        minhash=minhash,
        token_count=len(tokens),
        shingle_count=len(shingles),
    )


def estimate_lineage_similarity(
    left: ContentLineageFingerprint,
    right: ContentLineageFingerprint,
) -> float:
    if left.exact_signature == right.exact_signature and left.token_count > 0:
        return 1.0
    if not left.minhash or not right.minhash:
        return 0.0
    compared = min(len(left.minhash), len(right.minhash))
    if compared == 0:
        return 0.0
    matches = sum(
        left.minhash[index] == right.minhash[index]
        for index in range(compared)
    )
    return round(matches / compared, 4)


def fingerprint_metadata(value: ContentLineageFingerprint) -> dict[str, object]:
    return {
        "version": value.version,
        "exact_signature": value.exact_signature,
        "minhash": [str(item) for item in value.minhash],
        "token_count": value.token_count,
        "shingle_count": value.shingle_count,
    }


def fingerprint_from_metadata(metadata: object) -> ContentLineageFingerprint | None:
    if not isinstance(metadata, dict):
        return None
    exact = metadata.get("exact_signature")
    raw_minhash = metadata.get("minhash")
    token_count = metadata.get("token_count")
    shingle_count = metadata.get("shingle_count")
    if not isinstance(exact, str) or not isinstance(raw_minhash, list):
        return None
    try:
        minhash = tuple(int(item) for item in raw_minhash)
        tokens = int(token_count or 0)
        shingles = int(shingle_count or 0)
    except (TypeError, ValueError):
        return None
    return ContentLineageFingerprint(
        exact_signature=exact,
        minhash=minhash,
        token_count=tokens,
        shingle_count=shingles,
        version=str(metadata.get("version") or LINEAGE_FINGERPRINT_VERSION),
    )


def independence_cap_from_lineage_similarity(similarity: float) -> float:
    """Conservative independence cap for likely republished evidence.

    High content similarity does not prove copying, so this function only reduces the
    corroboration weight; it never changes evidence stance or factual status.
    """

    value = min(1.0, max(0.0, float(similarity)))
    if value >= 0.95:
        return 0.05
    if value >= 0.85:
        return 0.2
    if value >= 0.70:
        return 0.5
    return 1.0
