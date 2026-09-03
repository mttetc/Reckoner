"""Path of Exile adapter (SPEC § 8, adapter side).

Owns PoB parsing and the mapping onto the common domain.
"""

from __future__ import annotations

from app.domain.build import (
    BuildSnapshot,
    BuildVariant,
    Character,
    GameId,
    Modification,
    RawSource,
    SkillGem,
    SkillGroup,
    Tree,
)
from app.domain.errors import EngineUnavailable, InvalidBuildCode, InvalidModification
from app.domain.provenance import Metric, MetricKey, Provenance, ProvenanceStatus
from app.games.base import AdapterCapabilities
from app.games.poe.engine import EngineInfo, EngineStats, PobHeadless, get_engine
from app.games.poe.pob import codec
from app.games.poe.pob.items import parse_item_text
from app.games.poe.pob.stats import (
    MINION_STAT_MAP,
    PROVENANCE_CONFIG_KEYS,
    STAT_MAP,
    tree_version_to_patch,
)
from app.games.poe.pob.tree_url import decode_tree_url
from app.games.poe.pob.xml_parser import PobExport, parse_xml

ENGINE_NAME = "Path of Building"
SOURCE_EXPORT = (
    "pob:export"  # numbers PoB wrote into the export, by whatever version the author ran
)
SOURCE_HEADLESS = "pob:headless"  # numbers our pinned headless PoB computed just now


class PoEAdapter:
    game = GameId.POE
    display_name = "Path of Exile"

    def __init__(self, engine: PobHeadless | None = None) -> None:
        self._engine = engine

    @property
    def engine(self) -> PobHeadless:
        return self._engine if self._engine is not None else get_engine()

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            analyze_existing=True,
            recalculate_modified=self.engine.available(),  # honest: depends on the installed engine
            corpus_search=False,
            performance_observed=False,
        )

    def detect(self, payload: str) -> bool:
        if not codec.looks_like_code(payload):
            return False
        try:
            xml = codec.decode(payload)
        except Exception:
            return False
        # PoE1 and PoE2 exports share the <PathOfBuilding> root; the PoE2 adapter will refine
        # detection on its own markers. Until then, a PoB root means PoE1.
        return b"<PathOfBuilding" in xml[:512]

    def parse_build(self, payload: str) -> BuildSnapshot:
        xml = codec.decode(payload)
        export = parse_xml(xml)
        raw = RawSource.from_text("pob_code", "".join(payload.split()))
        return self._to_snapshot(
            export,
            raw,
            stats=export.stats,
            minion_stats=export.minion_stats,
            source=SOURCE_EXPORT,
            engine_version=None,  # PoB does not embed its own version in the export
            context={},
        )

    def recalculate(self, payload: str, modifications: list[Modification]) -> BuildVariant:
        """SPEC § 5 B: apply modifications inside headless PoB; never approximate.

        Returns the variant *and* a baseline computed by the same engine, because the export's
        own numbers may come from another PoB version and game-data patch.
        """
        if not self.engine.available():
            raise EngineUnavailable(
                "modified-build recalculation needs the headless Path of Building engine: "
                + self.engine.unavailable_reason()
            )
        if not modifications:
            raise InvalidModification("no modifications given")
        xml = codec.decode(payload)
        parent = self.parse_build(payload)
        mods = [{"kind": m.kind, "payload": m.payload} for m in modifications]
        info, base_stats, result = self.engine.evaluate_modified(xml.decode(), mods)
        raw = RawSource.from_text("pob_code", "".join(payload.split()))

        baseline = self._engine_snapshot(parse_xml(xml), raw, info, base_stats, applied=())
        variant = self._engine_snapshot(
            parse_xml(result.xml.encode()), raw, info, result.stats, applied=result.applied
        )
        return BuildVariant(
            parent_snapshot_id=parent.id,
            modifications=tuple(modifications),
            snapshot=variant,
            baseline=baseline,
        )

    def _engine_snapshot(
        self,
        export: PobExport,
        raw: RawSource,
        info: EngineInfo,
        stats: EngineStats,
        applied: tuple[dict, ...],
    ) -> BuildSnapshot:
        return self._to_snapshot(
            export,
            raw,
            stats=stats.player,
            minion_stats=stats.minion,
            source=SOURCE_HEADLESS,
            engine_version=info.engine_version,
            context={
                "engine_source_commit": info.source_commit,
                "engine_data_version": tree_version_to_patch(info.latest_tree_version),
                "modifications_applied": list(applied),
            },
        )

    def tree_geometry(self, version: str) -> dict:
        """Passive tree geometry for rendering (SPEC § 11 tree diffs). Engine-computed, cached."""
        if not self.engine.available():
            raise EngineUnavailable(
                "tree rendering needs the headless Path of Building engine: "
                + self.engine.unavailable_reason()
            )
        try:
            return self.engine.tree_geometry(version)
        except InvalidModification as exc:  # bridge refused the version
            raise InvalidBuildCode(str(exc)) from exc

    # ------------------------------------------------------------------ mapping

    def _to_snapshot(
        self,
        export: PobExport,
        raw: RawSource,
        *,
        stats: dict[str, float],
        minion_stats: dict[str, float],
        source: str,
        engine_version: str | None,
        context: dict,
    ) -> BuildSnapshot:
        patch = tree_version_to_patch(export.spec.tree_version if export.spec else None)
        skills = tuple(
            SkillGroup(
                slot=g.slot,
                enabled=g.enabled,
                label=g.label,
                gems=tuple(
                    SkillGem(
                        name=gem.name,
                        level=gem.level,
                        quality=gem.quality,
                        enabled=gem.enabled,
                        support=gem.is_support,
                    )
                    for gem in g.gems
                ),
            )
            for g in export.skill_groups
        )
        main_skill = self._main_skill(export)
        tree = self._tree(export)

        by_id = {it.id: it for it in export.items}
        items = tuple(
            parse_item_text(by_id[iid].text, slot)
            for slot, iid in export.slots.items()
            if iid in by_id
        )

        snapshot_id = None  # set after construction; provenance references it via snapshot.id below
        config_ctx = {k: v for k, v in export.config.items() if k in PROVENANCE_CONFIG_KEYS}
        base_prov = dict(
            status=ProvenanceStatus.CALCULATED,
            source=source,
            engine=ENGINE_NAME,
            engine_version=engine_version,
            game=self.game.value,
            game_version=patch,
            context={
                **context,
                "export_layout": export.layout,
                # PoB computes TotalDPS for whichever socket group the author left selected when
                # exporting. That selection may be a movement or utility skill; we report it as-is.
                "main_skill": main_skill,
                "main_skill_source": "socket group selected in the export",
                "engine_config": config_ctx,
            },
        )
        full_dps_breakdown = [
            {"skill": e.name, "value": e.value, "source": e.source, "part": e.skill_part}
            for e in export.full_dps
        ]

        metrics: list[Metric] = []
        for stat_name, key, unit in STAT_MAP:
            if stat_name in stats:
                prov = Provenance(snapshot_id=snapshot_id, **base_prov)
                if key is MetricKey.DPS_FULL and full_dps_breakdown:
                    # Say what the aggregate is made of; the number alone hides that.
                    prov = prov.model_copy(
                        update={
                            "context": {
                                **prov.context,
                                "aggregates": [e["skill"] for e in full_dps_breakdown],
                            }
                        }
                    )
                metrics.append(
                    Metric(key=key.value, value=stats[stat_name], unit=unit, provenance=prov)
                )
            elif stat_name in export.non_finite_stats:
                metrics.append(
                    Metric.unknown(
                        key.value,
                        f"engine reported a non-finite value for '{stat_name}' (inf/nan)",
                        unit=unit,
                    )
                )
            else:
                metrics.append(
                    Metric.unknown(
                        key.value, f"'{stat_name}' not present in this export", unit=unit
                    )
                )
        for stat_name, key, unit in MINION_STAT_MAP:
            if stat_name in minion_stats:
                metrics.append(
                    Metric(
                        key=key.value,
                        value=minion_stats[stat_name],
                        unit=unit,
                        provenance=Provenance(snapshot_id=snapshot_id, **base_prov),
                    )
                )

        snapshot = BuildSnapshot(
            game=self.game,
            game_version=patch,
            character=Character(
                class_name=export.header.class_name,
                subclass=export.header.ascend_class_name,
                level=export.header.level,
            ),
            main_skill=main_skill,
            skills=skills,
            items=items,
            tree=tree,
            engine_config=export.config,
            metrics=tuple(metrics),
            notes=export.notes,
            raw=raw,
            extra={
                "poe.bandit": export.header.bandit,
                "poe.pantheon_major": export.header.pantheon_major,
                "poe.pantheon_minor": export.header.pantheon_minor,
                "poe.pob_stats": stats,
                "poe.pob_minion_stats": minion_stats,
                "poe.full_dps_breakdown": full_dps_breakdown,
                "poe.pob_target_version": export.header.target_version,
            },
        )
        # Stamp the snapshot id into every provenance now that it exists (frozen models → rebuild).
        stamped = tuple(
            m.model_copy(
                update={
                    "provenance": m.provenance.model_copy(update={"snapshot_id": str(snapshot.id)})
                }
            )
            if m.provenance is not None
            else m
            for m in snapshot.metrics
        )
        return snapshot.model_copy(update={"metrics": stamped})

    @staticmethod
    def _main_skill(export: PobExport) -> str | None:
        idx = (export.header.main_socket_group or 1) - 1
        if not (0 <= idx < len(export.skill_groups)):
            return None
        group = export.skill_groups[idx]
        actives = [g for g in group.gems if g.enabled and g.is_support is not True]
        if not actives:
            return None
        a_idx = (group.main_active_skill or 1) - 1
        return actives[a_idx].name if 0 <= a_idx < len(actives) else actives[0].name

    @staticmethod
    def _tree(export: PobExport) -> Tree:
        spec = export.spec
        if spec is None:
            return Tree(unknown_reason="export has no <Tree><Spec>")
        if spec.nodes:
            return Tree(
                version=tree_version_to_patch(spec.tree_version),
                class_id=spec.class_id,
                subclass_id=spec.ascend_class_id,
                node_ids=spec.nodes,
                mastery_effects=spec.mastery_effects,
                source_url=spec.url,
            )
        if spec.url:
            decoded = decode_tree_url(spec.url)
            if decoded is not None:
                return Tree(
                    version=tree_version_to_patch(spec.tree_version),
                    class_id=decoded.class_id,
                    subclass_id=decoded.ascendancy_id,
                    node_ids=decoded.node_ids,
                    mastery_effects=decoded.mastery_effects,
                    source_url=spec.url,
                )
            return Tree(
                source_url=spec.url, unknown_reason="tree URL uses an unsupported encoding version"
            )
        return Tree(
            version=tree_version_to_patch(spec.tree_version),
            unknown_reason="no allocated nodes in export",
        )
