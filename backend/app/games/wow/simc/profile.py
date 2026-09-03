"""SimulationCraft addon profile → ``SimcProfile``. Plain ``key=value`` text, one field per line.

warrior="Thrall"
level=80
spec=fury
talents=BsQAAAAA…
head=,id=212002,bonus_id=6652/10356,enchant_id=7931
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.errors import InvalidBuildCode

CLASSES = {
    "deathknight",
    "demonhunter",
    "druid",
    "evoker",
    "hunter",
    "mage",
    "monk",
    "paladin",
    "priest",
    "rogue",
    "shaman",
    "warlock",
    "warrior",
}
SLOTS = (
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
    "shirt",
    "tabard",
    "wrist",
    "hands",
    "waist",
    "legs",
    "feet",
    "finger1",
    "finger2",
    "trinket1",
    "trinket2",
    "main_hand",
    "off_hand",
)
_CLASS_LINE = re.compile(r'^(?P<cls>[a-z_]+)="(?P<name>[^"]*)"\s*$')
_KV = re.compile(r"^(?P<key>[a-z_0-9]+)=(?P<value>.*)$")


@dataclass(frozen=True)
class SimcItem:
    slot: str
    item_id: int | None
    raw: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SimcProfile:
    class_name: str
    character_name: str | None
    spec: str | None
    level: int | None
    race: str | None
    talents: str | None
    fields: dict[str, str]
    items: tuple[SimcItem, ...]
    comments: tuple[str, ...]


def looks_like_profile(text: str) -> bool:
    head = "\n".join(text.strip().splitlines()[:40])
    return bool(re.search(r"^spec=\w+", head, re.M)) and bool(
        re.search(r"^(" + "|".join(sorted(CLASSES)) + r')="', head, re.M)
    )


def parse_profile(text: str) -> SimcProfile:
    class_name = character = None
    fields: dict[str, str] = {}
    items: list[SimcItem] = []
    comments: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            comments.append(line.lstrip("# ").strip())
            continue
        m = _CLASS_LINE.match(line)
        if m and class_name is None and m.group("cls") in CLASSES:
            class_name, character = m.group("cls"), m.group("name") or None
            continue
        m = _KV.match(line)
        if not m:
            continue
        key, value = m.group("key"), m.group("value")
        if key in SLOTS:
            parts = [p for p in value.split(",") if p]
            kv = dict(p.split("=", 1) for p in parts if "=" in p)
            item_id = int(kv["id"]) if kv.get("id", "").isdigit() else None
            items.append(SimcItem(slot=key, item_id=item_id, raw=value, fields=kv))
        else:
            fields.setdefault(key, value)
    if class_name is None:
        raise InvalidBuildCode(
            'not a SimulationCraft profile: no class line such as warrior="Name"'
        )
    level = int(fields["level"]) if fields.get("level", "").isdigit() else None
    return SimcProfile(
        class_name=class_name,
        character_name=character,
        spec=fields.get("spec"),
        level=level,
        race=fields.get("race"),
        talents=fields.get("talents"),
        fields=fields,
        items=tuple(items),
        comments=tuple(comments),
    )
