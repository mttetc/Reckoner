"""SimulationCraft for real (skips without RECKONER_SIMC_BIN). Numbers come from the engine."""

from pathlib import Path

import pytest

from app.domain.build import Modification
from app.domain.errors import InvalidModification
from app.domain.provenance import MetricKey
from app.games.wow.adapter import WowAdapter
from app.games.wow.simc.engine import SimcEngine

pytestmark = pytest.mark.skipif(
    not SimcEngine().available(), reason="SimulationCraft not installed"
)
FURY = (Path(__file__).parents[1] / "fixtures" / "wow" / "simc_warrior_fury_mid2.simc").read_text()


def test_simulation_yields_calculated_dps_with_engine_and_game_versions():
    ad = WowAdapter(engine=SimcEngine(iterations=200))
    assert ad.capabilities().recalculate_modified is True
    v = ad.recalculate(
        FURY, [Modification(kind="profile.set", payload={"key": "level", "value": 89})]
    )
    base = v.baseline.metric(MetricKey.DPS_TOTAL.value)
    var = v.snapshot.metric(MetricKey.DPS_TOTAL.value)
    assert base.value and base.value > 10_000
    assert var.value and var.value != base.value
    p = base.provenance
    assert p.status == "calculated" and p.engine == "SimulationCraft"
    assert p.engine_version and p.engine_version[0].isdigit()
    assert p.game_version and p.game_version.startswith("12.")
    assert p.context["iterations"] >= 200 and p.context["fight_style"] == "Patchwerk"
    # Gear detail comes from the engine: item levels the profile does not carry.
    assert any(it.item_level for it in v.baseline.items)
    assert v.snapshot.character.level == 89


def test_a_bad_talent_string_is_refused_by_the_engine_not_guessed():
    ad = WowAdapter(engine=SimcEngine(iterations=50))
    with pytest.raises(InvalidModification) as exc:
        ad.recalculate(
            FURY, [Modification(kind="talents.set", payload={"loadout": "AAAAAAAAAAAAAAAAAAAAAA"})]
        )
    assert "SimulationCraft refused" in str(exc.value)


def test_a_pasted_profile_is_simulated_as_is_and_its_talents_come_from_the_engine():
    ad = WowAdapter(engine=SimcEngine(iterations=100))
    snap = ad.parse_build(FURY)
    dps = snap.metric(MetricKey.DPS_TOTAL.value)
    assert dps.known and dps.provenance.engine == "SimulationCraft"
    assert snap.tree.unknown_reason is None and len(snap.tree.node_ids) > 60
    assert [g.label for g in snap.skills] == [
        "Warrior talents",
        "Fury talents",
        "Slayer (hero talents)",
    ]
    assert snap.extra["wow.talent_tables"][1]["talents"][0]["name"] == "Bloodthirst"
    assert snap.items[0].item_level and snap.items[0].item_level > 100


def test_talent_grid_comes_from_the_engine_data():
    ad = WowAdapter(engine=SimcEngine())
    grid = ad.talent_geometry("warrior", "fury")
    assert [t["kind"] for t in grid["trees"]] == ["class", "spec", "hero", "hero"]
    with pytest.raises(InvalidModification):
        ad.talent_geometry("warrior", "holy")
