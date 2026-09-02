"""Use case: analyse an existing build from a pasted code (SPEC § 5 A)."""

from __future__ import annotations

from app.domain.build import BuildSnapshot, GameId
from app.games import detect_adapter, get_adapter


def analyze_code(code: str, game: GameId | str | None = None) -> BuildSnapshot:
    adapter = get_adapter(game) if game else detect_adapter(code)
    return adapter.parse_build(code)
