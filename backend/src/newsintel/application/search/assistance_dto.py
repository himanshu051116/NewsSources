from __future__ import annotations

from pydantic import BaseModel, Field


class SearchAssistanceSuggestionView(BaseModel):
    kind: str
    replacement: str
    label: str
    reason: str
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class SearchAssistanceView(BaseModel):
    query: str
    normalized_query: str
    script: str
    language_filter_hint: str | None = None
    suggestions: list[SearchAssistanceSuggestionView] = Field(default_factory=list)
    guardrail: str = (
        "Suggestions never replace or execute the analyst query automatically. Applying a suggestion is an explicit user action."
    )
