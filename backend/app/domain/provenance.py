"""Provenance is a first-order domain concept (SPEC § 3).

Every displayed number carries a ``Provenance``. A number without one cannot be constructed:
``Metric`` refuses a value with no provenance, and ``Metric.unknown`` is the only way to express
"we do not know" — which is a valid result (SPEC § 3.9).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProvenanceStatus(StrEnum):
    OBSERVED = "observed"  # measured in the live game (rankings, clears)
    CALCULATED = "calculated"  # produced by a deterministic engine
    ESTIMATED = "estimated"  # only with an explicit, defensible methodology
    CLAIMED = "claimed"  # asserted by a third party; never conditions discovery


class Provenance(BaseModel):
    """Where a value comes from, precisely enough to trace it back (SPEC § 13.1)."""

    model_config = ConfigDict(frozen=True)

    status: ProvenanceStatus
    source: str = Field(
        description="Stable identifier of the origin, e.g. '<engine>:export', '<game>:ranking'."
    )
    engine: str | None = Field(
        default=None, description="Deterministic engine name when status is calculated."
    )
    engine_version: str | None = Field(
        default=None,
        description="Engine version if known. None means the origin did not embed it; "
        "it is never guessed.",
    )
    game: str = Field(
        description="Game identifier the value belongs to. Cross-game reuse is a bug (SPEC § 6)."
    )
    game_version: str | None = Field(
        default=None, description="Patch / tree version the value was produced under."
    )
    snapshot_id: str | None = Field(
        default=None, description="BuildSnapshot the value was derived from."
    )
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    methodology: str | None = Field(default=None, description="Mandatory when status is estimated.")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Conditions the value depends on, e.g. engine configuration (enemy type).",
    )

    @model_validator(mode="after")
    def _estimated_requires_methodology(self) -> Provenance:
        if self.status is ProvenanceStatus.ESTIMATED and not self.methodology:
            raise ValueError("estimated values require an explicit methodology (SPEC § 3)")
        return self


class Metric(BaseModel):
    """A single named quantity. Either known-with-provenance or explicitly unknown."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(
        description="Canonical metric key, e.g. 'dps.total', 'life.max'. See MetricKey."
    )
    value: float | None = None
    unit: str | None = None
    provenance: Provenance | None = None
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def _no_bare_numbers(self) -> Metric:
        if self.value is not None and self.provenance is None:
            raise ValueError(f"metric '{self.key}' has a value but no provenance (bare number)")
        if self.value is None and not self.unknown_reason:
            raise ValueError(f"metric '{self.key}' is unknown but gives no reason")
        return self

    @property
    def known(self) -> bool:
        return self.value is not None

    @classmethod
    def unknown(cls, key: str, reason: str, unit: str | None = None) -> Metric:
        return cls(key=key, value=None, unit=unit, unknown_reason=reason)


class MetricKey(StrEnum):
    """Canonical, game-neutral metric vocabulary. Adapters map their engine's names onto it.

    Keys are intentionally coarse: they are what the comparison / ranking layer reasons about.
    Anything game-specific stays in the adapter's own namespace (``<game>.*``).
    """

    DPS_TOTAL = "dps.total"
    DPS_COMBINED = "dps.combined"
    DPS_FULL = "dps.full"
    LIFE_MAX = "life.max"
    LIFE_UNRESERVED = "life.unreserved"
    ENERGY_SHIELD_MAX = "energy_shield.max"
    EHP_TOTAL = "ehp.total"
    MANA_MAX = "mana.max"
    MANA_UNRESERVED = "mana.unreserved"
    ARMOUR = "defence.armour"
    EVASION = "defence.evasion"
    BLOCK_CHANCE = "defence.block_chance"
    SPELL_BLOCK_CHANCE = "defence.spell_block_chance"
    PHYS_DAMAGE_REDUCTION = "defence.physical_damage_reduction"
    RES_FIRE = "resist.fire"
    RES_COLD = "resist.cold"
    RES_LIGHTNING = "resist.lightning"
    RES_CHAOS = "resist.chaos"
    SPEED = "offence.speed"
    CRIT_CHANCE = "offence.crit_chance"
    CRIT_MULTIPLIER = "offence.crit_multiplier"
    MOVEMENT_SPEED_MOD = "utility.movement_speed_mod"
    # Companion / summoned-entity metrics. Emitted only when the build's main skill has one.
    MINION_DPS_TOTAL = "minion.dps.total"
    MINION_LIFE_MAX = "minion.life.max"
    HPS_TOTAL = "hps.total"  # healing per second, where a game measures it
    DTPS_TOTAL = "dtps.total"  # damage taken per second
