"""World of Warcraft Classic adapter: WoWSims exporter JSON in, honest snapshots out.

Classic shares class and spell names with Retail but not the mechanics — the same collision as
PoE / PoE 2, handled by the mandatory ``game`` field everywhere.
"""

from __future__ import annotations

import json
import re

from app.domain.build import (
    BuildSnapshot,
    BuildVariant,
    Character,
    GameId,
    Item,
    Modification,
    RawSource,
    Tree,
)
from app.domain.errors import EngineUnavailable, InvalidBuildCode
from app.domain.provenance import Metric, MetricKey
from app.games.base import AdapterCapabilities

_TALENTS = re.compile(r"^[0-9]+(-[0-9]+){0,2}$")


class WowClassicAdapter:
    game = GameId.WOW_CLASSIC
    display_name = "World of Warcraft Classic"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            analyze_existing=True,
            recalculate_modified=False,  # WoWSims CLI not integrated yet
            corpus_search=False,
            performance_observed=False,
        )

    def detect(self, payload: str) -> bool:
        text = payload.strip()
        if not (text.startswith("{") and text.endswith("}")):
            return False
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return False
        return isinstance(data, dict) and "class" in data and ("talents" in data or "gear" in data)

    def parse_build(self, payload: str) -> BuildSnapshot:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise InvalidBuildCode(f"not a WoWSims export: {exc.msg}") from exc
        if not isinstance(data, dict) or "class" not in data:
            raise InvalidBuildCode("not a WoWSims export: missing 'class'")
        cls = str(data.get("class", "")).removeprefix("Class")
        race = str(data.get("race", "")).removeprefix("Race") or None
        talents = data.get("talents")
        talents = talents if isinstance(talents, str) and _TALENTS.match(talents) else None
        gear = data.get("gear") or {}
        raw_items = gear.get("items") if isinstance(gear, dict) else data.get("items")
        items = tuple(
            Item(
                slot=str(i),
                name=None,
                base_type=f"item {it.get('id')}" if it.get("id") else None,
                lines=[json.dumps(it, sort_keys=True)],
            )
            for i, it in enumerate(raw_items or [])
            if isinstance(it, dict)
        )
        metrics = tuple(
            Metric.unknown(
                key.value,
                "a WoWSims export carries no results; the WoWSims engine is not integrated yet",
                unit=unit,
            )
            for key, unit in ((MetricKey.DPS_TOTAL, "dps"), (MetricKey.LIFE_MAX, None))
        )
        return BuildSnapshot(
            game=self.game,
            game_version=str(data.get("gameVersion") or data.get("version") or "") or None,
            character=Character(
                class_name=cls or None,
                subclass=str(data.get("spec") or "").title() or None,
                level=int(data["level"]) if str(data.get("level", "")).isdigit() else None,
            ),
            items=items,
            tree=Tree(
                unknown_reason=(
                    "Classic talents are a digit string per tree; decoding needs the tree layout "
                    "data (not wired)"
                )
                if talents
                else "export has no talents"
            ),
            metrics=metrics,
            raw=RawSource.from_text("wowsims_export", payload.strip()),
            extra={
                "wow_classic.race": race,
                "wow_classic.talents": talents,
                "wow_classic.character": data.get("name"),
            },
        )

    def recalculate(self, payload: str, modifications: list[Modification]) -> BuildVariant:
        raise EngineUnavailable(
            "recalculation for Classic needs the WoWSims engine, which is not integrated"
        )
