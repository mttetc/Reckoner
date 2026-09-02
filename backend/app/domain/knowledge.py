"""Knowledge chunks for the RAG layer.

SPEC § 6: game-aware filtering is a correctness condition, not hygiene. Every chunk carries the
mandatory metadata below, and retrieval MUST filter on ``game`` before any similarity ranking.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    game: str
    version: str | None = None
    patch: str | None = None
    season: str | None = None
    class_name: str | None = None
    source: str = Field(description="Publisher / origin identifier, e.g. 'ggg:patch-notes'.")
    source_url: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    metadata: KnowledgeMetadata
