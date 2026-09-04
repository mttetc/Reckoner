"""World of Warcraft (Retail): SimulationCraft profiles in, provenance-first snapshots out."""

from __future__ import annotations

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
from app.domain.errors import EngineUnavailable, InvalidModification
from app.domain.provenance import Metric, MetricKey, Provenance, ProvenanceStatus
from app.games.base import AdapterCapabilities
from app.games.wow.simc.engine import SimcEngine, SimcFailed, SimcResult
from app.games.wow.simc.profile import SimcProfile, looks_like_profile, parse_profile
from app.games.wow.simc.talents import talent_grid

ENGINE_NAME = "SimulationCraft"
SOURCE_PROFILE = "simc:profile"
SOURCE_SIM = "simc:simulation"
HEADLINE_UNKNOWN = (
    (MetricKey.DPS_TOTAL, "dps"),
    (MetricKey.LIFE_MAX, None),
    (MetricKey.EHP_TOTAL, None),
)


class WowAdapter:
    game = GameId.WOW
    display_name = "World of Warcraft"

    def __init__(self, engine: SimcEngine | None = None) -> None:
        self._engine = engine
        self._results: dict[str, SimcResult] = {}  # profile text -> last simulation (small LRU)

    @property
    def engine(self) -> SimcEngine:
        return self._engine if self._engine is not None else SimcEngine()

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            analyze_existing=True,
            recalculate_modified=self.engine.available(),
            corpus_search=False,
            performance_observed=False,
        )

    def detect(self, payload: str) -> bool:
        return looks_like_profile(payload)

    def parse_build(self, payload: str) -> BuildSnapshot:
        """A profile describes the character and carries no results. With SimulationCraft
        installed the profile is simulated as-is and every number says so; without it, every
        number is unknown — and says why."""
        profile = parse_profile(payload)
        text = payload.strip()
        raw = RawSource.from_text("simc_profile", text)
        if self.engine.available():
            try:
                res = self._simulate(text)
            except SimcFailed as exc:
                reason = f"SimulationCraft could not simulate this profile: {exc}"
                return self._snapshot(profile, raw, self._unknown_metrics(reason))
            return self._snapshot(profile, raw, self._sim_metrics(res, []), res)
        reason = (
            "a SimulationCraft profile carries no results and SimulationCraft is not installed "
            f"({self.engine.unavailable_reason()})"
        )
        return self._snapshot(profile, raw, self._unknown_metrics(reason))

    def _unknown_metrics(self, reason: str) -> tuple[Metric, ...]:
        return tuple(Metric.unknown(key.value, reason, unit=unit) for key, unit in HEADLINE_UNKNOWN)

    def _simulate(self, text: str) -> SimcResult:
        key = f"{self.engine.binary}|{self.engine.iterations}|{text}"
        if key not in self._results:
            if len(self._results) >= 16:
                self._results.pop(next(iter(self._results)))
            self._results[key] = self.engine.simulate(text)
        return self._results[key]

    def talent_geometry(self, class_name: str, spec: str) -> dict:
        """The whole talent grid a specialisation can reach, from SimulationCraft's talent data."""
        if not self.engine.available():
            raise EngineUnavailable(
                "talent data needs the SimulationCraft engine: " + self.engine.unavailable_reason()
            )
        try:
            nodes = self.engine.talent_data(class_name)
        except SimcFailed as exc:
            raise InvalidModification(str(exc)) from exc
        grid = talent_grid(nodes, class_name, spec)
        if not grid["trees"][1]["nodes"]:
            raise InvalidModification(f"'{spec}' is not a {class_name} specialisation")
        return grid

    def recalculate(self, payload: str, modifications: list[Modification]) -> BuildVariant:
        """Modifications are applied to the profile text (SimulationCraft's own override syntax),
        then both the baseline and the variant are simulated by the same binary."""
        if not self.engine.available():
            raise EngineUnavailable(
                "recalculation needs the SimulationCraft engine: "
                + self.engine.unavailable_reason()
            )
        if not modifications:
            raise InvalidModification("no modifications given")
        profile = parse_profile(payload)
        base_text = payload.strip()
        variant_text = _apply(base_text, modifications)
        parent = self.parse_build(payload)
        try:
            base_res = self._simulate(base_text)
        except SimcFailed as exc:  # the unmodified profile itself is not simulatable
            raise EngineUnavailable(str(exc)) from exc
        try:
            var_res = self._simulate(variant_text)
        except SimcFailed as exc:  # the change is what SimulationCraft rejected
            raise InvalidModification(str(exc)) from exc
        raw = RawSource.from_text("simc_profile", base_text)
        baseline = self._snapshot(profile, raw, self._sim_metrics(base_res, []), base_res)
        variant = self._snapshot(
            parse_profile(variant_text),
            RawSource.from_text("simc_profile", variant_text),
            self._sim_metrics(var_res, [{"kind": m.kind, **m.payload} for m in modifications]),
            var_res,
        )
        return BuildVariant(
            parent_snapshot_id=parent.id,
            modifications=tuple(modifications),
            snapshot=variant,
            baseline=baseline,
        )

    # ------------------------------------------------------------------ mapping

    def _sim_metrics(self, res: SimcResult, applied: list[dict]) -> tuple[Metric, ...]:
        prov = Provenance(
            status=ProvenanceStatus.CALCULATED,
            source=SOURCE_SIM,
            engine=ENGINE_NAME,
            engine_version=res.version,
            game=self.game.value,
            game_version=res.game_version,
            context={
                "iterations": res.iterations,
                "fight_style": res.fight_style,
                "fight_length_s": res.fight_length,
                "dps_std_dev": res.dps_error,
                "modifications_applied": applied,
            },
        )
        out: list[Metric] = []
        if res.dps_mean is not None:
            out.append(
                Metric(
                    key=MetricKey.DPS_TOTAL.value, value=res.dps_mean, unit="dps", provenance=prov
                )
            )
        else:
            out.append(
                Metric.unknown(MetricKey.DPS_TOTAL.value, "the report carries no DPS", unit="dps")
            )
        if res.hps_mean is not None:
            out.append(
                Metric(
                    key=MetricKey.HPS_TOTAL.value, value=res.hps_mean, unit="hps", provenance=prov
                )
            )
        if res.dtps_mean is not None:
            out.append(
                Metric(
                    key=MetricKey.DTPS_TOTAL.value, value=res.dtps_mean, unit="dps", provenance=prov
                )
            )
        return tuple(out)

    def _snapshot(
        self,
        p: SimcProfile,
        raw: RawSource,
        metrics: tuple[Metric, ...],
        res: SimcResult | None = None,
    ) -> BuildSnapshot:
        # Item levels come from the engine when it ran (the profile only carries ids and bonuses).
        ilevels = {g.slot.replace("_", " "): g.ilevel for g in res.gear} if res else {}
        items = tuple(
            Item(
                slot=it.slot.replace("_", " "),
                name=it.name,
                base_type=f"item {it.item_id}" if it.item_id else None,
                rarity=None,
                item_level=(
                    int(it.fields["ilevel"])
                    if it.fields.get("ilevel", "").isdigit()
                    else ilevels.get(it.slot.replace("_", " "))
                ),
                lines=[it.raw],
            )
            for it in p.items
        )
        tables = res.talent_tables if res else ()
        if tables:
            # Node ids are the talents' spell ids, as SimulationCraft decoded the loadout.
            tree = Tree(
                version=res.game_version if res else None,
                node_ids=tuple(t.spell_id for tb in tables for t in tb.talents),
            )
        else:
            tree = Tree(
                unknown_reason=(
                    "talents not decoded: SimulationCraft did not run on this profile"
                    if p.talents
                    else "profile has no talents line"
                )
            )
        skills = tuple(
            SkillGroup(
                label=f"{tb.title} talents" if tb.kind != "hero" else f"{tb.title} (hero talents)",
                gems=tuple(SkillGem(name=t.name, level=t.rank) for t in tb.talents),
            )
            for tb in tables
        )
        return BuildSnapshot(
            game=self.game,
            game_version=res.game_version if res else None,
            character=Character(
                class_name=p.class_name.replace("_", " ").title(),
                subclass=(p.spec or "").title() or None,
                level=p.level,
            ),
            main_skill=None,
            skills=skills,
            items=items,
            tree=tree,
            engine_config={
                k: v
                for k, v in p.fields.items()
                if k in ("fight_style", "max_time", "target_error", "iterations")
            },
            metrics=metrics,
            notes="\n".join(p.comments) or None,
            raw=raw,
            extra={
                "wow.character": p.character_name,
                "wow.race": p.race,
                "wow.talents": p.talents,
                "wow.talent_tables": [tb.to_dict() for tb in tables],
                "wow.profession": p.fields.get("professions"),
            },
        )


def _apply(profile_text: str, modifications: list[Modification]) -> str:
    """Supported kinds: ``profile.set {key, value}`` (a SimulationCraft key=value override) and
    ``talents.set {loadout}``. Anything else is refused explicitly — never silently ignored."""
    lines = profile_text.splitlines()

    def set_key(key: str, value: str) -> None:
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                return
        lines.append(f"{key}={value}")

    for m in modifications:
        if m.kind == "profile.set":
            key, value = m.payload.get("key"), m.payload.get("value")
            if not key or value is None or not str(key).replace("_", "").isalnum():
                raise InvalidModification("profile.set needs a simple key and a value")
            set_key(str(key), str(value))
        elif m.kind == "talents.set":
            loadout = m.payload.get("loadout")
            if not loadout or not str(loadout).isalnum():
                raise InvalidModification("talents.set needs a talent loadout string")
            set_key("talents", str(loadout))
        else:
            raise InvalidModification(
                f"unsupported modification kind '{m.kind}' for World of Warcraft"
            )
    return "\n".join(lines) + "\n"
