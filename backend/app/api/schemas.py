from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.build import BuildSnapshot, BuildVariant, GameId, Modification
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


class GameInfo(BaseModel):
    id: GameId
    display_name: str
    capabilities: AdapterCapabilities


class ErrorBody(BaseModel):
    code: str
    message: str
