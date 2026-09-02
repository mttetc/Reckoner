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
from app.domain.errors import EngineUnavailable
from app.domain.provenance import Metric, Provenance, ProvenanceStatus
from app.games.base import AdapterCapabilities
from app.games.poe.pob import codec
from app.games.poe.pob.items import parse_item_text
from app.games.poe.pob.stats import PROVENANCE_CONFIG_KEYS, STAT_MAP, tree_version_to_patch
from app.games.poe.pob.tree_url import decode_tree_url
from app.games.poe.pob.xml_parser import PobExport, parse_xml

ENGINE_NAME = "Path of Building"
SOURCE_ID = "pob:export"


class PoEAdapter:
    game = GameId.POE
    display_name = "Path of Exile"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            analyze_existing=True,
            recalculate_modified=False,  # headless PoB not wired yet — see docs/DECISIONS.md
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
        return self._to_snapshot(export, raw)

    def recalculate(
        self, snapshot: BuildSnapshot, modifications: list[Modification]
    ) -> BuildVariant:
        raise EngineUnavailable(
            "modified-build recalculation requires the headless Path of Building engine, "
            "which is not integrated yet (SPEC § 5 B). No approximation is offered."
        )

    # ------------------------------------------------------------------ mapping

    def _to_snapshot(self, export: PobExport, raw: RawSource) -> BuildSnapshot:
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
            source=SOURCE_ID,
            engine=ENGINE_NAME,
            engine_version=None,  # PoB does not embed its own version in the export
            game=self.game.value,
            game_version=patch,
            context={
                "export_layout": export.layout,
                "main_skill": main_skill,
                "engine_config": config_ctx,
            },
        )

        metrics: list[Metric] = []
        for stat_name, key, unit in STAT_MAP:
            if stat_name in export.stats:
                metrics.append(
                    Metric(
                        key=key.value,
                        value=export.stats[stat_name],
                        unit=unit,
                        provenance=Provenance(snapshot_id=snapshot_id, **base_prov),
                    )
                )
            else:
                metrics.append(
                    Metric.unknown(
                        key.value, f"'{stat_name}' not present in this export", unit=unit
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
                "poe.pob_stats": export.stats,
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
