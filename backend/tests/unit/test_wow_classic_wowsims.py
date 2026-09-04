"""WoW Classic through WoWSims: the export is read, the request is the UI's, numbers the CLI's."""

import json
import stat
from pathlib import Path

import pytest

from app.config import settings
from app.domain.build import Modification
from app.domain.errors import EngineUnavailable, InvalidModification
from app.domain.provenance import MetricKey
from app.games import detect_adapter
from app.games.wow_classic.adapter import WowClassicAdapter
from app.games.wow_classic.wowsims.data import WowSimsData, field_to_name
from app.games.wow_classic.wowsims.engine import WowSimsEngine
from app.games.wow_classic.wowsims.settings import (
    looks_like_settings,
    parse_settings,
    set_path,
    talent_points,
    to_raid_sim_request,
)

FIX = Path(__file__).parents[1] / "fixtures" / "wow"
SETTINGS = (FIX / "wowsims_fury_warrior_settings.json").read_text()
ADDON = (FIX / "fury_warrior_classic.json").read_text()
DATA = WowSimsData(FIX / "wowsims_data")


def test_the_sim_page_export_is_recognised_and_read():
    assert looks_like_settings(SETTINGS) and not looks_like_settings(ADDON)
    assert detect_adapter(SETTINGS).game.value == "wow_classic"
    s = parse_settings(SETTINGS)
    assert (s.class_name, s.race, s.spec_key) == ("Warrior", "Orc", "warrior")
    assert len(s.items) == 17 and s.items[0].slot == "head" and s.items[0].item_id == 12640
    assert s.items[14].slot == "main hand" and s.iterations == 500 and s.duration == 120


def test_talent_string_digits_are_points_per_tree():
    assert talent_points("30305001302-05050005525010051") == [17, 34, 0]
    assert talent_points(None) == [0, 0, 0]


def test_the_request_is_the_ui_assembly_not_an_interpretation():
    data = json.loads(SETTINGS)
    req = to_raid_sim_request(data, 250)
    assert req["raid"]["parties"][0]["players"][0] is data["player"]
    assert req["raid"]["buffs"] == data["raidBuffs"] and req["encounter"] == data["encounter"]
    assert req["simOptions"]["iterations"] == 250


def test_set_path_edits_a_copy_and_refuses_typos():
    data = json.loads(SETTINGS)
    out = set_path(data, "encounter.duration", 60)
    assert out["encounter"]["duration"] == 60 and data["encounter"]["duration"] == 120
    with pytest.raises(InvalidModification):
        set_path(data, "encunter.duration", 60)


def test_wowsims_data_names_items_and_decodes_talents_from_its_tree_files():
    assert DATA.item(12640)["name"] == "Lionheart Helm"
    trees = DATA.decode_talents("Warrior", "30305001302-05050005525010051")
    assert [t.name for t in trees] == ["Arms", "Fury", "Protection"]
    assert [t.points for t in trees] == [17, 34, 0]
    taken = [x for x in trees[1].talents if x.rank]
    assert taken[0].name == "Cruelty" and taken[0].rank == 5 and taken[0].row == 1
    assert field_to_name("improvedHeroicStrike") == "Improved Heroic Strike"
    assert all(x.node_id == 1000 + x.index + 1 for x in trees[1].talents)


def test_without_wowsims_the_export_is_read_honestly(monkeypatch):
    monkeypatch.setattr(settings, "wowsims_bin", None)
    ad = WowClassicAdapter(engine=WowSimsEngine(binary=None), data=DATA)
    assert ad.capabilities().recalculate_modified is False
    s = ad.parse_build(SETTINGS)
    assert s.character.class_name == "Warrior" and s.character.subclass == "Fury"
    assert s.items[0].name == "Lionheart Helm" and s.items[0].item_level
    dps = s.metric(MetricKey.DPS_TOTAL.value)
    assert dps.value is None and "WoWSims is not installed" in dps.unknown_reason
    assert [g.label for g in s.skills] == ["Arms talents", "Fury talents"]
    assert len(s.tree.node_ids) == sum(
        1 for t in s.extra["wow.talent_tables"] for _ in t["talents"]
    )
    with pytest.raises(EngineUnavailable):
        ad.recalculate(
            SETTINGS, [Modification(kind="encounter.set", payload={"key": "duration", "value": 60})]
        )


def test_the_addon_export_is_described_but_never_simulated(monkeypatch):
    monkeypatch.setattr(settings, "wowsims_bin", None)
    ad = WowClassicAdapter(engine=WowSimsEngine(binary=None), data=DATA)
    s = ad.parse_build(ADDON)
    assert s.character.class_name == "Warrior"
    assert "sim page" in s.metric(MetricKey.DPS_TOTAL.value).unknown_reason


@pytest.fixture
def fake_wowsimcli(tmp_path: Path) -> str:
    """A stand-in CLI: DPS = 10 × encounter duration, so a change is traceable to its cause."""
    script = tmp_path / "wowsimcli"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "version" ]; then echo fake123; exit 0; fi\n'
        "python3 - <<'PY'\n"
        "import json\n"
        "req = json.load(open('input.json'))\n"
        "d = req['encounter']['duration']\n"
        "dps = {'avg': d * 10, 'stdev': 1.5}\n"
        "print(json.dumps({'raidMetrics': {'parties': [{'players': [{'dps': dps}]}]},"
        " 'iterationsDone': req['simOptions']['iterations']}))\n"
        "PY\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_recalculation_simulates_baseline_and_variant_with_the_same_binary(fake_wowsimcli):
    ad = WowClassicAdapter(engine=WowSimsEngine(binary=fake_wowsimcli, iterations=9), data=DATA)
    assert ad.capabilities().recalculate_modified is True
    snap = ad.parse_build(SETTINGS)
    assert snap.metric(MetricKey.DPS_TOTAL.value).value == 1200.0
    v = ad.recalculate(
        SETTINGS, [Modification(kind="encounter.set", payload={"key": "duration", "value": 60})]
    )
    base = v.baseline.metric(MetricKey.DPS_TOTAL.value)
    var = v.snapshot.metric(MetricKey.DPS_TOTAL.value)
    assert base.value == 1200.0 and var.value == 600.0
    for m in (base, var):
        assert m.provenance.status == "calculated" and m.provenance.engine == "WoWSims Classic"
        assert m.provenance.engine_version == "fake123" and m.provenance.context["iterations"] == 9
    assert var.provenance.context["modifications_applied"] == [
        {"kind": "encounter.set", "key": "duration", "value": 60}
    ]
    with pytest.raises(InvalidModification):
        ad.recalculate(SETTINGS, [Modification(kind="gem.set_level", payload={})])
    with pytest.raises(InvalidModification):
        ad.recalculate(
            ADDON, [Modification(kind="encounter.set", payload={"key": "duration", "value": 60})]
        )
