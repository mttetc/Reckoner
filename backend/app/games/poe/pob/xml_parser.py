"""PoB XML → ``PobExport``. Handles both the pre-2020 layout and the current one.

Old layout (PoB 1.4 era)           Current layout (PoB Community 2.x)
  <Skills><Skill><Gem/>              <Skills activeSkillSet><SkillSet id><Skill><Gem/>
  <Items><Item/><Slot/>              <Items activeItemSet><Item/><ItemSet id><Slot/>
  <Config><Input/>                   <Config activeConfigSet><ConfigSet id><Input/>
  <Tree><Spec><URL/>                 <Tree><Spec treeVersion nodes masteryEffects classId …>

Nothing here interprets numbers: values are carried as exported. Interpretation (canonical metrics,
provenance) happens in ``stats.py`` / ``adapter.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from app.domain.errors import InvalidBuildCode

_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=True
)


@dataclass(frozen=True)
class PobHeader:
    level: int | None
    class_name: str | None
    ascend_class_name: str | None
    target_version: str | None
    bandit: str | None
    pantheon_major: str | None
    pantheon_minor: str | None
    main_socket_group: int | None


@dataclass(frozen=True)
class PobGem:
    name: str
    skill_id: str | None
    gem_id: str | None
    level: int | None
    quality: int | None
    enabled: bool

    @property
    def is_support(self) -> bool | None:
        if self.gem_id:
            return "/SupportGem" in self.gem_id or "Support" in self.gem_id.rsplit("/", 1)[-1][:7]
        if self.skill_id:
            return self.skill_id.startswith("Support")
        return None


@dataclass(frozen=True)
class PobSkillGroup:
    slot: str | None
    label: str | None
    enabled: bool
    main_active_skill: int | None
    gems: tuple[PobGem, ...]


@dataclass(frozen=True)
class PobItem:
    id: int
    text: str


@dataclass(frozen=True)
class PobSpec:
    tree_version: str | None
    class_id: int | None
    ascend_class_id: int | None
    nodes: tuple[int, ...]
    mastery_effects: dict[int, int]
    url: str | None


@dataclass(frozen=True)
class PobExport:
    header: PobHeader
    stats: dict[str, float]
    skill_groups: tuple[PobSkillGroup, ...]
    items: tuple[PobItem, ...]
    slots: dict[str, int]  # slot name → item id (active item set)
    spec: PobSpec | None
    config: dict[str, Any]
    notes: str | None
    layout: str = field(default="modern")  # or "legacy" — useful for provenance context


def _int(v: str | None) -> int | None:
    if v is None or v in ("", "nil"):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _bool(v: str | None, default: bool = True) -> bool:
    if v is None:
        return default
    return v.lower() == "true"


def parse_xml(xml: bytes) -> PobExport:
    try:
        root = etree.fromstring(xml, _PARSER)
    except etree.XMLSyntaxError as exc:
        raise InvalidBuildCode(f"malformed XML: {exc.msg}") from exc
    if root.tag != "PathOfBuilding":
        raise InvalidBuildCode(f"unexpected root element <{root.tag}>")
    build = root.find("Build")
    if build is None:
        raise InvalidBuildCode("missing <Build> element")

    header = PobHeader(
        level=_int(build.get("level")),
        class_name=build.get("className"),
        ascend_class_name=build.get("ascendClassName"),
        target_version=build.get("targetVersion"),
        bandit=build.get("bandit"),
        pantheon_major=build.get("pantheonMajorGod"),
        pantheon_minor=build.get("pantheonMinorGod"),
        main_socket_group=_int(build.get("mainSocketGroup")),
    )

    stats: dict[str, float] = {}
    for ps in build.findall("PlayerStat"):
        name, value = ps.get("stat"), ps.get("value")
        if not name or value is None or name in stats:
            continue  # legacy exports repeat some stats; keep the first occurrence
        try:
            stats[name] = float(value)
        except ValueError:
            continue

    skills_el = root.find("Skills")
    layout = "modern"
    groups: list[PobSkillGroup] = []
    if skills_el is not None:
        sets = skills_el.findall("SkillSet")
        if sets:
            active = skills_el.get("activeSkillSet") or "1"
            chosen = next((s for s in sets if s.get("id") == active), sets[0])
            skill_els = chosen.findall("Skill")
        else:
            layout = "legacy"
            skill_els = skills_el.findall("Skill")
        for s in skill_els:
            gems = tuple(
                PobGem(
                    name=g.get("nameSpec") or g.get("skillId") or "?",
                    skill_id=g.get("skillId"),
                    gem_id=g.get("gemId"),
                    level=_int(g.get("level")),
                    quality=_int(g.get("quality")),
                    enabled=_bool(g.get("enabled")),
                )
                for g in s.findall("Gem")
            )
            groups.append(
                PobSkillGroup(
                    slot=s.get("slot") or None,
                    label=s.get("label") or None,
                    enabled=_bool(s.get("enabled")),
                    main_active_skill=_int(s.get("mainActiveSkill")),
                    gems=gems,
                )
            )

    items: list[PobItem] = []
    slots: dict[str, int] = {}
    items_el = root.find("Items")
    if items_el is not None:
        for it in items_el.findall("Item"):
            iid = _int(it.get("id"))
            if iid is not None:
                items.append(PobItem(id=iid, text=(it.text or "").strip()))
        sets = items_el.findall("ItemSet")
        if sets:
            active = items_el.get("activeItemSet") or "1"
            chosen = next((s for s in sets if s.get("id") == active), sets[0])
            slot_els = chosen.findall("Slot")
        else:
            slot_els = items_el.findall("Slot")
        for sl in slot_els:
            iid = _int(sl.get("itemId"))
            name = sl.get("name")
            if name and iid:
                slots[name] = iid

    spec: PobSpec | None = None
    tree_el = root.find("Tree")
    if tree_el is not None:
        specs = tree_el.findall("Spec")
        if specs:
            active = tree_el.get("activeSpec") or "1"
            idx = (_int(active) or 1) - 1
            s = specs[idx] if 0 <= idx < len(specs) else specs[0]
            nodes_attr = s.get("nodes") or ""
            nodes = tuple(int(n) for n in nodes_attr.split(",") if n.strip().isdigit())
            masteries: dict[int, int] = {}
            for node, effect in re.findall(r"\{(\d+),(\d+)\}", s.get("masteryEffects") or ""):
                masteries[int(node)] = int(effect)
            url_el = s.find("URL")
            spec = PobSpec(
                tree_version=s.get("treeVersion"),
                class_id=_int(s.get("classId")),
                ascend_class_id=_int(s.get("ascendClassId")),
                nodes=nodes,
                mastery_effects=masteries,
                url=(url_el.text or "").strip() if url_el is not None else None,
            )

    config: dict[str, Any] = {}
    cfg_el = root.find("Config")
    if cfg_el is not None:
        sets = cfg_el.findall("ConfigSet")
        if sets:
            active = cfg_el.get("activeConfigSet") or "1"
            chosen = next((s for s in sets if s.get("id") == active), sets[0])
            inputs = chosen.findall("Input")
        else:
            inputs = cfg_el.findall("Input")
        for inp in inputs:
            name = inp.get("name")
            if not name:
                continue
            if inp.get("boolean") is not None:
                config[name] = inp.get("boolean") == "true"
            elif inp.get("number") is not None:
                try:
                    config[name] = float(inp.get("number"))
                except ValueError:
                    config[name] = inp.get("number")
            else:
                config[name] = inp.get("string")

    notes_el = root.find("Notes")
    notes = (notes_el.text or "").strip() if notes_el is not None else None

    return PobExport(
        header=header,
        stats=stats,
        skill_groups=tuple(groups),
        items=tuple(items),
        slots=slots,
        spec=spec,
        config=config,
        notes=notes or None,
        layout=layout,
    )
