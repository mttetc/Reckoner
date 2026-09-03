from fastapi import APIRouter, HTTPException

from app.api.schemas import GameInfo
from app.domain.build import GameId
from app.games import get_adapter, list_adapters

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=list[GameInfo])
def games() -> list[GameInfo]:
    return [
        GameInfo(id=a.game, display_name=a.display_name, capabilities=a.capabilities())
        for a in list_adapters()
    ]


@router.get("/{game}/tree/{version}")
def tree_geometry(game: GameId, version: str) -> dict:
    """Passive tree geometry for one version, as the game engine computes it. 503 without engine."""
    adapter = get_adapter(game)
    fn = getattr(adapter, "tree_geometry", None)
    if fn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_available", "message": f"{game.value} has no tree geometry"},
        )
    return fn(version)
