"""WoWSims "Export → JSON" payloads (``IndividualSimSettings`` in protojson) and the raid-sim
request built from them — the same structural assembly the WoWSims UI does before it simulates
(``makeRaidSimRequest``). Nothing here interprets game mechanics."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass

from app.domain.errors import InvalidBuildCode, InvalidModification

# proto/api.proto: the `oneof spec` keys of Player, in protojson camelCase.
SPEC_KEYS = (
    "balanceDruid",
    "feralDruid",
    "feralTankDruid",
    "restorationDruid",
    "hunter",
    "mage",
    "retributionPaladin",
    "protectionPaladin",
    "holyPaladin",
    "healingPriest",
    "shadowPriest",
    "rogue",
    "elementalShaman",
    "enhancementShaman",
    "restorationShaman",
    "wardenShaman",
    "warlock",
    "warrior",
    "tankWarrior",
)
# proto/common.proto ItemSlot order: EquipmentSpec.items is indexed by slot.
SLOT_NAMES = (
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
    "wrist",
    "hands",
    "waist",
    "legs",
    "feet",
    "finger 1",
    "finger 2",
    "trinket 1",
    "trinket 2",
    "main hand",
    "off hand",
    "ranged",
)
_TALENTS = re.compile(r"^[0-9]*(-[0-9]*){0,2}$")


@dataclass(frozen=True)
class SettingsItem:
    slot: str
    item_id: int | None
    enchant_id: int | None
    gems: tuple[int, ...]
    raw: dict


@dataclass(frozen=True)
class SimSettings:
    data: dict
    player: dict
    name: str | None
    class_name: str | None  # "Warrior"
    race: str | None  # "Orc"
    spec_key: str | None  # "warrior" | "tankWarrior" | …
    talents_string: str | None
    items: tuple[SettingsItem, ...]
    iterations: int | None
    duration: float | None
    phase: int | None


def _load(text: str) -> dict | None:
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def looks_like_settings(text: str) -> bool:
    data = _load(text)
    player = data.get("player") if data else None
    return (
        isinstance(player, dict)
        and "class" in player
        and ("equipment" in player or "talentsString" in player)
    )


def parse_settings(text: str) -> SimSettings:
    data = _load(text)
    if data is None or not isinstance(data.get("player"), dict):
        raise InvalidBuildCode(
            "not a WoWSims settings export: expected a JSON object with 'player'"
        )
    player = data["player"]
    if "class" not in player:
        raise InvalidBuildCode("not a WoWSims settings export: the player has no 'class'")
    items = []
    for i, it in enumerate((player.get("equipment") or {}).get("items") or []):
        if not isinstance(it, dict):
            continue
        items.append(
            SettingsItem(
                slot=SLOT_NAMES[i] if i < len(SLOT_NAMES) else f"slot {i}",
                item_id=int(it["id"]) if isinstance(it.get("id"), int) and it["id"] else None,
                enchant_id=int(it["enchant"]) if isinstance(it.get("enchant"), int) else None,
                gems=tuple(g for g in it.get("gems", []) if isinstance(g, int)),
                raw=it,
            )
        )
    talents = player.get("talentsString")
    talents = talents if isinstance(talents, str) and _TALENTS.match(talents) else None
    sim = data.get("settings") or {}
    enc = data.get("encounter") or {}
    return SimSettings(
        data=data,
        player=player,
        name=player.get("name") or None,
        class_name=str(player["class"]).removeprefix("Class") or None,
        race=str(player.get("race", "")).removeprefix("Race") or None,
        spec_key=next((k for k in SPEC_KEYS if k in player), None),
        talents_string=talents,
        items=tuple(items),
        iterations=int(sim["iterations"]) if isinstance(sim.get("iterations"), int) else None,
        duration=float(enc["duration"]) if isinstance(enc.get("duration"), int | float) else None,
        phase=int(sim["phase"]) if isinstance(sim.get("phase"), int) else None,
    )


def talent_points(talents_string: str | None) -> list[int]:
    """'30305001302-05050005525010051' → [17, 34, 0]: points per tree, digits per talent."""
    parts = (talents_string or "").split("-")
    points = [sum(int(c) for c in p if c.isdigit()) for p in parts]
    return (points + [0, 0, 0])[:3]


def to_raid_sim_request(data: dict, iterations: int) -> dict:
    """IndividualSimSettings → RaidSimRequest, field for field, as the WoWSims UI does."""
    return {
        "raid": {
            "parties": [{"players": [data["player"]], "buffs": data.get("partyBuffs") or {}}],
            "buffs": data.get("raidBuffs") or {},
            "debuffs": data.get("debuffs") or {},
            "tanks": data.get("tanks") or [],
            "targetDummies": data.get("targetDummies") or 0,
        },
        "encounter": data.get("encounter") or {},
        "simOptions": {"iterations": iterations, "randomSeed": "1"},
    }


def set_path(data: dict, path: str, value: object) -> dict:
    """A copy of ``data`` with the dotted ``path`` set (``player.talentsString``,
    ``encounter.duration``). Intermediate objects must exist: a typo is refused, never created."""
    out = copy.deepcopy(data)
    keys = path.split(".")
    cur: object = out
    for key in keys[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            raise InvalidModification(f"no '{key}' in the export at '{path}'")
        cur = cur[key]
    if not isinstance(cur, dict):
        raise InvalidModification(f"'{path}' does not point into an object")
    cur[keys[-1]] = value
    return out
