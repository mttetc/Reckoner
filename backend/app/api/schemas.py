from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.build import BuildSnapshot, BuildVariant, Character, GameId, Modification
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
