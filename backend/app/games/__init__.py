"""Adapter registry. Adding a game = adding a package here and one line in ``_ADAPTERS``."""

from __future__ import annotations

from app.domain.build import GameId
from app.domain.errors import InvalidBuildCode, UnsupportedGame
from app.games.base import GameAdapter
from app.games.poe.adapter import PoEAdapter

_ADAPTERS: dict[GameId, GameAdapter] = {
    GameId.POE: PoEAdapter(),
}


def list_adapters() -> list[GameAdapter]:
    return list(_ADAPTERS.values())


def get_adapter(game: GameId | str) -> GameAdapter:
    try:
        return _ADAPTERS[GameId(game)]
    except (KeyError, ValueError) as exc:
        raise UnsupportedGame(f"no adapter registered for game '{game}'") from exc


def detect_adapter(payload: str) -> GameAdapter:
    matches = [a for a in _ADAPTERS.values() if a.detect(payload)]
    if len(matches) != 1:
        raise InvalidBuildCode(
            "could not attribute the payload to exactly one game"
            + (f" (candidates: {[a.game for a in matches]})" if matches else "")
        )
    return matches[0]
