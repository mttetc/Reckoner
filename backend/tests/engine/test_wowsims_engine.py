"""WoWSims Classic for real (skips without RECKONER_WOWSIMS_BIN). Numbers come from the CLI."""

from pathlib import Path

import pytest

from app.domain.build import Modification
from app.domain.errors import InvalidModification
from app.domain.provenance import MetricKey
from app.games.wow_classic.adapter import WowClassicAdapter
from app.games.wow_classic.wowsims.engine import WowSimsEngine

pytestmark = pytest.mark.skipif(not WowSimsEngine().available(), reason="wowsimcli not installed")
SETTINGS = (
    Path(__file__).parents[1] / "fixtures" / "wow" / "wowsims_fury_warrior_settings.json"
).read_text()


def test_a_pasted_export_is_simulated_as_is_with_names_and_talents_from_the_simulator():
    ad = WowClassicAdapter(engine=WowSimsEngine(iterations=200))
    snap = ad.parse_build(SETTINGS)
    dps = snap.metric(MetricKey.DPS_TOTAL.value)
    assert dps.known and dps.value > 1000 and dps.provenance.engine == "WoWSims Classic"
    assert dps.provenance.engine_version and dps.provenance.context["iterations"] >= 200
    assert snap.character.subclass == "Fury" and snap.items[0].name == "Lionheart Helm"
    assert [g.label for g in snap.skills] == ["Arms talents", "Fury talents"]
    assert len(snap.tree.node_ids) >= 10  # talents taken, one node per talent


def test_a_shorter_fight_is_simulated_again_and_an_unknown_item_is_refused():
    ad = WowClassicAdapter(engine=WowSimsEngine(iterations=200))
    v = ad.recalculate(
        SETTINGS, [Modification(kind="encounter.set", payload={"key": "duration", "value": 45})]
    )
    assert (
        v.baseline.metric(MetricKey.DPS_TOTAL.value).value
        != v.snapshot.metric(MetricKey.DPS_TOTAL.value).value
    )
    with pytest.raises(InvalidModification) as exc:
        ad.recalculate(
            SETTINGS,
            [
                Modification(
                    kind="settings.set",
                    payload={"path": "player.equipment.items", "value": [{"id": 1}]},
                )
            ],
        )
    assert "WoWSims refused" in str(exc.value)


def test_talent_grid_comes_from_the_simulator_data():
    grid = WowClassicAdapter().talent_geometry("warrior", "fury")
    assert [t["kind"] for t in grid["trees"]] == ["arms", "fury", "protection"]
    assert sum(len(t["nodes"]) for t in grid["trees"]) == 52
