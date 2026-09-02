from fastapi import APIRouter

from app.api.schemas import GameInfo
from app.games import list_adapters

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=list[GameInfo])
def games() -> list[GameInfo]:
    return [
        GameInfo(id=a.game, display_name=a.display_name, capabilities=a.capabilities())
        for a in list_adapters()
    ]
