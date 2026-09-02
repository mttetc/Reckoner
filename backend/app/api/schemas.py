from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.build import BuildSnapshot, GameId
from app.games.base import AdapterCapabilities


class AnalyzeRequest(BaseModel):
    code: str = Field(min_length=1, description="Build sharing code (e.g. a PoB export).")
    game: GameId | None = Field(
        default=None, description="Force a game; auto-detected when omitted."
    )


class AnalyzeResponse(BaseModel):
    snapshot: BuildSnapshot


class GameInfo(BaseModel):
    id: GameId
    display_name: str
    capabilities: AdapterCapabilities


class ErrorBody(BaseModel):
    code: str
    message: str
