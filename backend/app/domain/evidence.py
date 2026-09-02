"""Evidence: a citable fact backing a statement in an answer (SPEC § 3, § 10)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.provenance import Provenance


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    statement: str = Field(description="What the evidence supports, in one sentence.")
    provenance: Provenance
    source_url: str | None = None
    excerpt: str | None = Field(
        default=None, description="Short quote; never whole copyrighted passages."
    )
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
