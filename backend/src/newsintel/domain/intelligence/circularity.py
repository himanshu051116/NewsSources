from __future__ import annotations

import re
from dataclasses import dataclass

CIRCULAR_SOURCING_VERSION = "circular-sourcing-detector-v1"


@dataclass(frozen=True, slots=True)
class CircularSourcingAssessment:
    detector_version: str
    detected: bool
    independence_cap: float
    matched_reference: str | None
    rationale: str


def detect_circular_sourcing(
    evidence_text: str,
    *,
    origin_publisher_name: str | None = None,
    origin_domain: str | None = None,
) -> CircularSourcingAssessment:
    """Detect explicit attribution back to the originating publisher/source.

    This intentionally looks only for explicit sourcing language. A shared topic or matching
    wording is not enough to call reporting circular.
    """
    text = " ".join(evidence_text.casefold().split())
    references = [
        value.strip().casefold()
        for value in (origin_publisher_name, origin_domain)
        if isinstance(value, str) and value.strip()
    ]
    verbs = r"(?:according to|reported by|reports from|citing|as reported by|told)"
    for reference in references:
        escaped = re.escape(reference)
        patterns = (
            rf"{verbs}\s+(?:the\s+)?{escaped}\b",
            rf"\b{escaped}\b.{{0,50}}\b(?:reported|said|stated|according to)\b",
        )
        if any(re.search(pattern, text, re.I) for pattern in patterns):
            return CircularSourcingAssessment(
                detector_version=CIRCULAR_SOURCING_VERSION,
                detected=True,
                independence_cap=0.15,
                matched_reference=reference,
                rationale=(
                    "The evidence explicitly attributes the relevant reporting back to the "
                    "originating publisher/source. It may still provide context, but should "
                    "not be counted as independent corroboration."
                ),
            )
    return CircularSourcingAssessment(
        detector_version=CIRCULAR_SOURCING_VERSION,
        detected=False,
        independence_cap=1.0,
        matched_reference=None,
        rationale="No explicit circular attribution to the originating source was detected.",
    )
