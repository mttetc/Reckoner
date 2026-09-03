"""Build, BuildSnapshot, BuildVariant — the common representation every adapter normalises to.

SPEC § 3.8: build history is never overwritten. A ``Build`` is an identity; every import or
modification appends a ``BuildSnapshot``. A ``BuildVariant`` is a snapshot derived from another
by an explicit list of modifications, whose metrics come from a real recalculation (SPEC § 5 B).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.provenance import Metric


class GameId(StrEnum):
    """Known games. Adding a value here is the *only* common-domain change a new adapter needs."""

    POE = "poe"
    POE2 = "poe2"
    DIABLO3 = "diablo3"
    WOW = "wow"
    WOW_CLASSIC = "wow_classic"


class RawSource(BaseModel):
    """Fingerprint of the input the snapshot was parsed from. We keep the hash, not the paste."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(description="Input kind as named by the adapter, e.g. '<engine>_code'.")
    sha256: str
    size_bytes: int
    url: str | None = Field(
        default=None, description="Public origin URL when ingested from a permitted source."
    )

    @classmethod
    def from_text(cls, kind: str, text: str, url: str | None = None) -> RawSource:
        data = text.encode()
        return cls(kind=kind, sha256=sha256(data).hexdigest(), size_bytes=len(data), url=url)


class Character(BaseModel):
    model_config = ConfigDict(frozen=True)

    class_name: str | None = None
    subclass: str | None = Field(
        default=None, description="Game-specific specialisation of the class, if the game has one."
    )
    level: int | None = None


class SkillGem(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    level: int | None = None
    quality: int | None = None
    enabled: bool = True
    support: bool | None = None


class SkillGroup(BaseModel):
    model_config = ConfigDict(frozen=True)

    slot: str | None = None
    enabled: bool = True
    label: str | None = None
    gems: tuple[SkillGem, ...] = ()


class Item(BaseModel):
    model_config = ConfigDict(frozen=True)

    slot: str | None = None
    name: str | None = None
    base_type: str | None = None
    rarity: str | None = None
    item_level: int | None = None
    lines: tuple[str, ...] = Field(
        default=(), description="Raw item text lines as exported; no interpretation."
    )


class Tree(BaseModel):
    """Allocated passives.

    Node ids are opaque to the common domain; the adapter owns their meaning.
    """

    model_config = ConfigDict(frozen=True)

    version: str | None = None
    class_id: int | None = None
    subclass_id: int | None = None
    node_ids: tuple[int, ...] = ()
    mastery_effects: dict[int, int] = Field(default_factory=dict)
    source_url: str | None = None
    unknown_reason: str | None = Field(
        default=None, description="Set when allocated nodes could not be recovered from the input."
    )


class BuildSnapshot(BaseModel):
    """Immutable, normalised view of one build state at one moment."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    game: GameId
    game_version: str | None = Field(
        default=None, description="Patch or tree version the snapshot targets."
    )
    character: Character = Field(default_factory=Character)
    main_skill: str | None = None
    skills: tuple[SkillGroup, ...] = ()
    items: tuple[Item, ...] = ()
    tree: Tree = Field(default_factory=Tree)
    engine_config: dict[str, Any] = Field(
        default_factory=dict, description="Engine configuration the metrics were produced under."
    )
    metrics: tuple[Metric, ...] = ()
    notes: str | None = None
    raw: RawSource
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = Field(
        default_factory=dict, description="Adapter-specific data, namespaced by game."
    )

    def metric(self, key: str) -> Metric | None:
        return next((m for m in self.metrics if m.key == key), None)


class Modification(BaseModel):
    """One requested change to a build.

    Applying it never produces metrics by itself (SPEC § 3.15).
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(
        description="Adapter-defined, e.g. 'tree.allocate', 'tree.deallocate', 'item.replace'."
    )
    payload: dict[str, Any] = Field(default_factory=dict)


class BuildVariant(BaseModel):
    """A snapshot derived from a parent through explicit modifications and a real recalculation."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    parent_snapshot_id: UUID
    modifications: tuple[Modification, ...]
    snapshot: BuildSnapshot
    baseline: BuildSnapshot | None = Field(
        default=None,
        description=(
            "The parent re-evaluated by the same engine version with no modification. Deltas "
            "between `baseline` and `snapshot` are like-for-like; deltas against the parent's own "
            "metrics may include engine/data drift."
        ),
    )


class Build(BaseModel):
    """Identity of a build across time. Snapshots are append-only."""

    id: UUID = Field(default_factory=uuid4)
    game: GameId
    name: str | None = None
    snapshot_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
