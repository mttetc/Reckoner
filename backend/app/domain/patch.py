"""Patch / version awareness (SPEC § 3.6). Versions are strings owned by each game's adapter."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class Patch(BaseModel):
    model_config = ConfigDict(frozen=True)

    game: str
    version: str = Field(description="Canonical version label, e.g. '3.27'.")
    season: str | None = Field(
        default=None, description="League / season name if the game has them."
    )
    released_on: date | None = None
    source_url: str | None = None
