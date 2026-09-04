"""World of Warcraft Classic adapter: WoWSims payloads in, provenance-first snapshots out.

Two payloads exist. The addon exporter JSON describes a character (class, gear ids, talents) and
cannot be simulated: it has no rotation, buffs or encounter. The sim page's "Export → JSON"
(``IndividualSimSettings``) has everything WoWSims needs, so it is simulated as-is by the WoWSims
CLI when installed. Classic shares class and spell names with Retail but not the mechanics — the
same collision as PoE / PoE 2, handled by the mandatory ``game`` field everywhere.
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
    SkillGem,
    SkillGroup,
    Tree,
)
from app.domain.errors import EngineUnavailable, InvalidBuildCode, InvalidModification
from app.domain.provenance import Metric, MetricKey, Provenance, ProvenanceStatus
from app.games.base import AdapterCapabilities
from app.games.wow_classic.wowsims.data import ClassicTree, WowSimsData
from app.games.wow_classic.wowsims.engine import WowSimsEngine, WowSimsFailed, WowSimsResult
from app.games.wow_classic.wowsims.settings import (
    SimSettings,
    looks_like_settings,
    parse_settings,
    set_path,
)

ENGINE_NAME = "WoWSims Classic"
SOURCE_SIM = "wowsims:simulation"
_TALENTS = re.compile(r"^[0-9]+(-[0-9]+){0,2}$")
HEADLINE_UNKNOWN = ((MetricKey.DPS_TOTAL, "dps"), (MetricKey.LIFE_MAX, None))


class WowClassicAdapter:
    game = GameId.WOW_CLASSIC
    display_name = "World of Warcraft Classic"

    def __init__(self, engine: WowSimsEngine | None = None, data: WowSimsData | None = None):
        self._engine = engine
        self._data = data
        self._results: dict[str, WowSimsResult] = {}

    @property
    def engine(self) -> WowSimsEngine:
        return self._engine if self._engine is not None else WowSimsEngine()

    @property
    def data(self) -> WowSimsData:
        if self._data is None:
            self._data = WowSimsData.locate(self.engine.binary)
        return self._data

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            analyze_existing=True,
            recalculate_modified=self.engine.available(),
            corpus_search=False,
            performance_observed=False,
        )

    # ------------------------------------------------------------------ detect / parse

    def detect(self, payload: str) -> bool:
        return looks_like_settings(payload) or _looks_like_addon_export(payload)

    def parse_build(self, payload: str) -> BuildSnapshot:
        if looks_like_settings(payload):
            return self._from_settings(payload)
        return self._from_addon_export(payload)

    def _from_settings(self, payload: str) -> BuildSnapshot:
        s = parse_settings(payload)
        text = payload.strip()
        raw = RawSource.from_text("wowsims_settings", text)
        if self.engine.available():
            try:
                res = self._simulate(text, s.data)
            except WowSimsFailed as exc:
                return self._snapshot(
                    s, raw, self._unknown(f"WoWSims could not simulate this export: {exc}")
                )
            return self._snapshot(s, raw, self._sim_metrics(res, []), res)
        reason = (
            "a WoWSims export carries no results and WoWSims is not installed "
            f"({self.engine.unavailable_reason()})"
        )
        return self._snapshot(s, raw, self._unknown(reason))

    def _from_addon_export(self, payload: str) -> BuildSnapshot:
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
                name=(self.data.item(it["id"]) or {}).get("name")
                if isinstance(it.get("id"), int)
                else None,
                base_type=f"item {it.get('id')}" if it.get("id") else None,
                lines=[json.dumps(it, sort_keys=True)],
            )
            for i, it in enumerate(raw_items or [])
            if isinstance(it, dict)
        )
        trees = self.data.decode_talents(cls, talents) if cls and talents else []
        return BuildSnapshot(
            game=self.game,
            game_version=str(data.get("gameVersion") or data.get("version") or "") or None,
            character=Character(
                class_name=cls or None,
                subclass=str(data.get("spec") or "").title() or _dominant(trees),
                level=int(data["level"]) if str(data.get("level", "")).isdigit() else None,
            ),
            skills=_skills(trees),
            items=items,
            tree=_tree(trees, talents),
            metrics=self._unknown(
                "the addon export carries no results, rotation, buffs or encounter; export the "
                "JSON from the WoWSims sim page to have it simulated"
            ),
            raw=RawSource.from_text("wowsims_export", payload.strip()),
            extra={
                "wow_classic.race": race,
                "wow_classic.talents": talents,
                "wow_classic.character": data.get("name"),
                "wow.talent_tables": [t.to_table() for t in trees],
            },
        )

    # ------------------------------------------------------------------ recalculate

    def recalculate(self, payload: str, modifications: list[Modification]) -> BuildVariant:
        """Modifications edit the export (WoWSims' own settings), then baseline and variant are
        both simulated by the same binary. Supported: ``talents.set {loadout}``,
        ``encounter.set {key, value}``, ``settings.set {path, value}``."""
        if not self.engine.available():
            raise EngineUnavailable(
                "recalculation for Classic needs the WoWSims engine: "
                + self.engine.unavailable_reason()
            )
        if not looks_like_settings(payload):
            raise InvalidModification(
                "only the sim page's JSON export can be simulated; the addon export lacks the "
                "rotation, buffs and encounter"
            )
        if not modifications:
            raise InvalidModification("no modifications given")
        base = parse_settings(payload)
        variant_data = _apply(base.data, modifications)
        variant_text = json.dumps(variant_data, indent=1)
        variant = parse_settings(variant_text)
        parent = self.parse_build(payload)
        try:
            base_res = self._simulate(payload.strip(), base.data)
        except WowSimsFailed as exc:
            raise EngineUnavailable(str(exc)) from exc
        try:
            var_res = self._simulate(variant_text, variant_data)
        except WowSimsFailed as exc:  # the change is what WoWSims rejected
            raise InvalidModification(str(exc)) from exc
        applied = [{"kind": m.kind, **m.payload} for m in modifications]
        baseline = self._snapshot(
            base,
            RawSource.from_text("wowsims_settings", payload.strip()),
            self._sim_metrics(base_res, []),
            base_res,
        )
        snapshot = self._snapshot(
            variant,
            RawSource.from_text("wowsims_settings", variant_text),
            self._sim_metrics(var_res, applied),
            var_res,
        )
        return BuildVariant(
            parent_snapshot_id=parent.id,
            snapshot=snapshot,
            baseline=baseline,
            modifications=tuple(modifications),
        )

    def talent_geometry(self, class_name: str, spec: str) -> dict:
        """Every talent of the class's three trees, from WoWSims' tree data (Classic trees are per
        class; ``spec`` only names the dominant tree)."""
        trees = self.data.decode_talents(class_name, None)
        if not trees:
            raise EngineUnavailable(
                f"no WoWSims talent data for '{class_name}' (RECKONER_WOWSIMS_SRC / checkout)"
            )
        return {
            "class_name": class_name.lower(),
            "spec": spec.lower(),
            "trees": [
                {
                    "kind": t.name.lower(),
                    "subtree": None,
                    "rows": t.rows,
                    "columns": t.columns,
                    "nodes": [
                        {
                            "node": x.node_id,
                            "row": x.row,
                            "col": x.col,
                            "max_rank": x.max_rank,
                            "choices": [{"name": x.name, "spell_id": x.node_id}],
                        }
                        for x in t.talents
                    ],
                }
                for t in trees
            ],
        }

    # ------------------------------------------------------------------ mapping

    def _simulate(self, text: str, data: dict) -> WowSimsResult:
        key = f"{self.engine.binary}|{self.engine.iterations}|{text}"
        if key not in self._results:
            if len(self._results) >= 16:
                self._results.pop(next(iter(self._results)))
            self._results[key] = self.engine.simulate(data)
        return self._results[key]

    def _unknown(self, reason: str) -> tuple[Metric, ...]:
        return tuple(Metric.unknown(k.value, reason, unit=u) for k, u in HEADLINE_UNKNOWN)

    def _sim_metrics(self, res: WowSimsResult, applied: list[dict]) -> tuple[Metric, ...]:
        prov = Provenance(
            status=ProvenanceStatus.CALCULATED,
            source=SOURCE_SIM,
            engine=ENGINE_NAME,
            engine_version=res.version,
            game=self.game.value,
            game_version=None,
            context={
                "iterations": res.iterations,
                "fight_length_s": res.duration,
                "dps_std_dev": res.dps_stdev,
                "modifications_applied": applied,
            },
        )
        out: list[Metric] = []
        if res.dps_avg is not None:
            out.append(
                Metric(
                    key=MetricKey.DPS_TOTAL.value, value=res.dps_avg, unit="dps", provenance=prov
                )
            )
        else:
            out.append(
                Metric.unknown(MetricKey.DPS_TOTAL.value, "the result carries no DPS", unit="dps")
            )
        if res.hps_avg:
            out.append(
                Metric(
                    key=MetricKey.HPS_TOTAL.value, value=res.hps_avg, unit="hps", provenance=prov
                )
            )
        if res.dtps_avg:
            out.append(
                Metric(
                    key=MetricKey.DTPS_TOTAL.value, value=res.dtps_avg, unit="dps", provenance=prov
                )
            )
        return tuple(out)

    def _snapshot(
        self,
        s: SimSettings,
        raw: RawSource,
        metrics: tuple[Metric, ...],
        res: WowSimsResult | None = None,
    ) -> BuildSnapshot:
        items = []
        for it in s.items:
            info = self.data.item(it.item_id) if it.item_id else None
            items.append(
                Item(
                    slot=it.slot,
                    name=(info or {}).get("name"),
                    base_type=f"item {it.item_id}" if it.item_id else None,
                    rarity=_quality((info or {}).get("quality")),
                    item_level=(info or {}).get("ilvl"),
                    lines=[json.dumps(it.raw, sort_keys=True)],
                )
            )
        trees = self.data.decode_talents(s.class_name, s.talents_string) if s.class_name else []
        return BuildSnapshot(
            game=self.game,
            game_version=None,
            character=Character(
                class_name=s.class_name,
                subclass=_dominant(trees) or _spec_label(s.spec_key),
                level=60,  # Classic Era characters are simulated at the level cap
            ),
            main_skill=None,
            skills=_skills(trees),
            items=tuple(items),
            tree=_tree(trees, s.talents_string),
            engine_config={
                "iterations": s.iterations,
                "duration": s.duration,
                "phase": s.phase,
            },
            metrics=metrics,
            raw=raw,
            extra={
                "wow_classic.race": s.race,
                "wow_classic.talents": s.talents_string,
                "wow_classic.character": s.name,
                "wow_classic.spec_key": s.spec_key,
                "wow.talent_tables": [t.to_table() for t in trees],
            },
        )


def _looks_like_addon_export(payload: str) -> bool:
    text = payload.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return False
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and "class" in data and ("talents" in data or "gear" in data)


def _dominant(trees: list[ClassicTree]) -> str | None:
    if not trees or not any(t.points for t in trees):
        return None
    return max(trees, key=lambda t: t.points).name


def _spec_label(spec_key: str | None) -> str | None:
    if not spec_key:
        return None
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", spec_key).split()
    return " ".join(w.title() for w in words)


def _skills(trees: list[ClassicTree]) -> tuple[SkillGroup, ...]:
    return tuple(
        SkillGroup(
            label=f"{t.name} talents",
            gems=tuple(SkillGem(name=x.name, level=x.rank) for x in t.talents if x.rank > 0),
        )
        for t in trees
        if t.points
    )


def _tree(trees: list[ClassicTree], talents: str | None) -> Tree:
    if trees:
        return Tree(node_ids=tuple(x.node_id for t in trees for x in t.talents if x.rank > 0))
    if talents:
        return Tree(
            unknown_reason="Classic talents are a digit string per tree; the tree layout comes "
            "from the WoWSims checkout, which is not available here"
        )
    return Tree(unknown_reason="export has no talents")


def _quality(q: object) -> str | None:
    names = {0: "Poor", 1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary"}
    return names.get(q) if isinstance(q, int) else None


def _apply(data: dict, modifications: list[Modification]) -> dict:
    out = data
    for m in modifications:
        p = m.payload
        if m.kind == "talents.set":
            if not isinstance(p.get("loadout"), str) or not _TALENTS.match(p["loadout"]):
                raise InvalidModification(
                    "talents.set needs a WoWSims talent string like '30305001302-05050005525010051'"
                )
            out = set_path(out, "player.talentsString", p["loadout"])
        elif m.kind == "encounter.set":
            if not isinstance(p.get("key"), str) or "value" not in p:
                raise InvalidModification("encounter.set needs {key, value}")
            out = set_path(out, f"encounter.{p['key']}", p["value"])
        elif m.kind == "settings.set":
            if not isinstance(p.get("path"), str) or "value" not in p:
                raise InvalidModification("settings.set needs {path, value}")
            out = set_path(out, p["path"], p["value"])
        else:
            raise InvalidModification(
                f"unsupported modification '{m.kind}' for Classic; "
                "use talents.set, encounter.set or settings.set"
            )
    return out
