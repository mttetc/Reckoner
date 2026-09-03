"""Use case: what-if on an existing build, computed by a real engine (SPEC § 5 B)."""

from __future__ import annotations

from app.domain.build import BuildVariant, GameId, Modification
from app.games import detect_adapter, get_adapter


def recalculate_code(
    code: str, modifications: list[Modification], game: GameId | str | None = None
) -> BuildVariant:
    adapter = get_adapter(game) if game else detect_adapter(code)
    return adapter.recalculate(code, modifications)
