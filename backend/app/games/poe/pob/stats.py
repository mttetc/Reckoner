"""PoB ``PlayerStat`` names → canonical ``MetricKey``. Purely a renaming table plus units."""

from __future__ import annotations

from app.domain.provenance import MetricKey

# (pob stat name, canonical key, unit)
STAT_MAP: tuple[tuple[str, MetricKey, str | None], ...] = (
    ("TotalDPS", MetricKey.DPS_TOTAL, "dps"),
    ("CombinedDPS", MetricKey.DPS_COMBINED, "dps"),
    ("FullDPS", MetricKey.DPS_FULL, "dps"),
    ("Life", MetricKey.LIFE_MAX, None),
    ("LifeUnreserved", MetricKey.LIFE_UNRESERVED, None),
    ("EnergyShield", MetricKey.ENERGY_SHIELD_MAX, None),
    ("TotalEHP", MetricKey.EHP_TOTAL, None),
    ("Mana", MetricKey.MANA_MAX, None),
    ("ManaUnreserved", MetricKey.MANA_UNRESERVED, None),
    ("Armour", MetricKey.ARMOUR, None),
    ("Evasion", MetricKey.EVASION, None),
    ("BlockChance", MetricKey.BLOCK_CHANCE, "%"),
    ("SpellBlockChance", MetricKey.SPELL_BLOCK_CHANCE, "%"),
    ("PhysicalDamageReduction", MetricKey.PHYS_DAMAGE_REDUCTION, "%"),
    ("FireResist", MetricKey.RES_FIRE, "%"),
    ("ColdResist", MetricKey.RES_COLD, "%"),
    ("LightningResist", MetricKey.RES_LIGHTNING, "%"),
    ("ChaosResist", MetricKey.RES_CHAOS, "%"),
    ("Speed", MetricKey.SPEED, "/s"),
    ("CritChance", MetricKey.CRIT_CHANCE, "%"),
    ("CritMultiplier", MetricKey.CRIT_MULTIPLIER, "x"),
    ("EffectiveMovementSpeedMod", MetricKey.MOVEMENT_SPEED_MOD, "x"),
)

# ``MinionStat`` rows → canonical keys. Optional: a build without minions has no such rows, and
# their absence is *not* an unknown — there is simply no minion to measure.
MINION_STAT_MAP: tuple[tuple[str, MetricKey, str | None], ...] = (
    ("TotalDPS", MetricKey.MINION_DPS_TOTAL, "dps"),
    ("Life", MetricKey.MINION_LIFE_MAX, None),
)

# Configuration inputs that materially condition calculated values; they belong in provenance.
PROVENANCE_CONFIG_KEYS: tuple[str, ...] = (
    "enemyIsBoss",
    "conditionStationary",
    "conditionFullLife",
    "buffOnslaught",
    "usePowerCharges",
    "useFrenzyCharges",
    "useEnduranceCharges",
    "conditionEnemyShocked",
    "multiplierNearbyEnemies",
    "enemyLevel",
)


def tree_version_to_patch(tree_version: str | None) -> str | None:
    """'3_27' → '3.27'. Returns None when the export does not embed a tree version."""
    if not tree_version:
        return None
    return tree_version.replace("_", ".")
