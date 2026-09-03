"""Contract every game adapter implements.

The common domain never imports from ``app.games.<game>``; adapters depend on the domain only.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.domain.build import BuildSnapshot, BuildVariant, GameId, Modification


class AdapterCapabilities(BaseModel):
    """What the adapter can honestly do today. Drives degraded states in the API (SPEC § 13.8)."""

    analyze_existing: bool  # SPEC § 5 A
    recalculate_modified: bool  # SPEC § 5 B — requires a real headless engine
    corpus_search: bool
    performance_observed: bool


@runtime_checkable
class GameAdapter(Protocol):
    game: GameId
    display_name: str

    def capabilities(self) -> AdapterCapabilities: ...

    def detect(self, payload: str) -> bool:
        """Cheap check: does this payload look like something this adapter parses?"""
        ...

    def parse_build(self, payload: str) -> BuildSnapshot:
        """SPEC § 5 A. Raises ``InvalidBuildCode`` on undecodable input."""
        ...

    def recalculate(self, payload: str, modifications: list[Modification]) -> BuildVariant:
        """SPEC § 5 B. Re-parses ``payload`` (snapshots keep a hash, not the paste), applies the
        modifications inside a real engine and returns the variant plus a same-engine baseline.
        Must raise ``EngineUnavailable`` when no engine is configured — never approximate.
        """
        ...
