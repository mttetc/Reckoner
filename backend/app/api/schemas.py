from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.build import BuildSnapshot, BuildVariant, Character, GameId, Modification
from app.domain.evidence import Evidence
from app.domain.knowledge import KnowledgeChunk
from app.domain.provenance import Metric
from app.games.base import AdapterCapabilities


class AnalyzeRequest(BaseModel):
    code: str = Field(min_length=1, description="Build sharing code (e.g. a PoB export).")
    game: GameId | None = Field(
        default=None, description="Force a game; auto-detected when omitted."
    )


class AnalyzeResponse(BaseModel):
    snapshot: BuildSnapshot


class RecalculateRequest(BaseModel):
    code: str = Field(min_length=1, description="Build sharing code the variant derives from.")
    game: GameId | None = None
    modifications: list[Modification] = Field(
        min_length=1,
        description=(
            "Adapter-defined changes, e.g. {kind: 'tree.deallocate', payload: {node_id: 41119}}."
        ),
    )


class RecalculateResponse(BaseModel):
    variant: BuildVariant


class SourceInfo(BaseModel):
    kind: str
    url: str
    title: str | None = None
    parent_url: str | None = None
    terms: str | None = Field(default=None, description="Why fetching this source was permitted.")


class BuildSummary(BaseModel):
    snapshot_id: UUID
    game: GameId
    game_version: str | None
    character: Character
    main_skill: str | None
    metrics: list[Metric] = Field(description="Headline metrics, each with provenance or unknown.")
    node_count: int | None
    created_at: datetime
    source: SourceInfo | None


class SearchResponse(BaseModel):
    total: int
    items: list[BuildSummary]


class BuildDetail(BaseModel):
    snapshot: BuildSnapshot
    source: SourceInfo | None


class KnowledgeHit(BaseModel):
    chunk: KnowledgeChunk
    heading: str | None
    title: str | None
    score: float = Field(description="Cosine similarity, informational; never a game number.")


class PatchInfo(BaseModel):
    patch: str
    published_at: datetime | None
    chunks: int
    source_url: str


class KnowledgeStats(BaseModel):
    chunks: int
    per_game: dict[str, int]
    embedders: list[str]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    game: GameId | None = Field(
        default=None, description="Hint; the agent still passes it to tools."
    )
    code: str | None = Field(default=None, description="Optional build code to reason about.")


class StepView(BaseModel):
    tool: str
    args: dict[str, Any]
    ok: bool
    summary: str
    error: str | None
    duration_ms: int


class AuditView(BaseModel):
    checked: int = Field(description="Numbers found in the answer.")
    unverified: list[str] = Field(
        description="Numbers that match no tool result — shown, never hidden."
    )
    clean: bool


class FeedbackRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=128)
    rating: str = Field(pattern="^(positive|negative)$")
    question: str | None = Field(default=None, max_length=2000)
    answer: str | None = Field(default=None, max_length=8000)


class AskResponse(BaseModel):
    suggestions: list[str] = Field(
        default_factory=list, description="Follow-up questions to offer."
    )
    answer: str
    model: str = Field(description="Provider and model that orchestrated; 'scripted' = no model.")
    steps: list[StepView]
    evidence: list[Evidence]
    audit: AuditView
    degraded: list[str]
    input_tokens: int
    output_tokens: int
    duration_ms: int


class CorpusStats(BaseModel):
    snapshots: int
    sources: int
    per_game: dict[str, int]
    per_version: list[dict[str, Any]]


class GameInfo(BaseModel):
    id: GameId
    display_name: str
    capabilities: AdapterCapabilities


class ErrorBody(BaseModel):
    code: str
    message: str
