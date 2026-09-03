"""World of Warcraft, Retail and Classic: the abstraction test of SPEC § 8, made concrete."""

import os
import stat
from pathlib import Path

import pytest

from app.domain.build import GameId, Modification
from app.domain.errors import EngineUnavailable, InvalidBuildCode, InvalidModification
from app.domain.provenance import MetricKey
from app.games import detect_adapter, get_adapter, list_adapters
from app.games.wow.adapter import WowAdapter
from app.games.wow.simc.engine import SimcEngine

FIX = Path(__file__).parents[1] / "fixtures" / "wow"
RETAIL = (FIX / "fury_warrior.simc").read_text()
CLASSIC = (FIX / "fury_warrior_classic.json").read_text()


def test_registry_lists_both_games():
    ids = {a.game for a in list_adapters()}
    assert {GameId.WOW, GameId.WOW_CLASSIC} <= ids


def test_detection_routes_each_payload_to_exactly_one_game(code_modern):
    assert detect_adapter(RETAIL).game == GameId.WOW
    assert detect_adapter(CLASSIC).game == GameId.WOW_CLASSIC
    assert detect_adapter(code_modern).game == GameId.POE
    with pytest.raises(InvalidBuildCode):
        detect_adapter("hello there")


def test_retail_profile_parses_into_the_common_domain():
    s = get_adapter("wow").parse_build(RETAIL)
    assert s.game == GameId.WOW
    assert (
        s.character.class_name == "Warrior"
        and s.character.subclass == "Fury"
        and s.character.level == 80
    )
    assert len(s.items) == 6 and s.items[0].slot == "head" and s.items[0].item_level == 639
    assert s.extra["wow.talents"].startswith("BsQ")
    dps = s.metric(MetricKey.DPS_TOTAL.value)
    assert dps.value is None and "run a simulation" in dps.unknown_reason
    assert s.tree.unknown_reason and "Blizzard" in s.tree.unknown_reason
    assert s.raw.kind == "simc_profile"


def test_classic_export_parses_into_the_common_domain():
    s = get_adapter("wow_classic").parse_build(CLASSIC)
    assert s.game == GameId.WOW_CLASSIC
    assert (
        s.character.class_name == "Warrior"
        and s.character.subclass == "Fury"
        and s.character.level == 60
    )
    assert len(s.items) == 2
    assert s.extra["wow_classic.talents"] == "30305001302-05050005525010051"
    assert s.metric(MetricKey.DPS_TOTAL.value).value is None
    with pytest.raises(EngineUnavailable):
        get_adapter("wow_classic").recalculate(
            CLASSIC, [Modification(kind="profile.set", payload={})]
        )


def test_retail_without_simulationcraft_refuses_to_guess():
    ad = WowAdapter(engine=SimcEngine(binary=None))
    assert ad.capabilities().recalculate_modified is False
    with pytest.raises(EngineUnavailable) as exc:
        ad.recalculate(
            RETAIL, [Modification(kind="profile.set", payload={"key": "level", "value": 79})]
        )
    assert "RECKONER_SIMC_BIN" in str(exc.value)


@pytest.fixture
def fake_simc(tmp_path: Path) -> str:
    """A stand-in binary that writes a SimulationCraft-shaped json2 report. DPS depends on the
    profile's level line so the variant differs from the baseline in a traceable way."""
    script = tmp_path / "simc"
    script.write_text(
        "#!/bin/sh\n"
        "profile=$1; out=$(printf '%s\\n' \"$@\" | sed -n 's/^json2=//p')\n"
        "level=$(sed -n 's/^level=//p' \"$profile\")\n"
        "dps=$((level * 1000))\n"
        'cat > "$out" <<EOF\n'
        '{"version": "1130-01", "sim": {"options": {"iterations": 7, "max_time": 300},'
        ' "players": [{"name": "Reckoner", "collected_data": '
        '{"dps": {"mean": $dps.5, "mean_std_dev": 12.5},'
        ' "dtps": {"mean": 4200.0}}}]}}\n'
        "EOF\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    os.environ["PATH"] = f"{tmp_path}:{os.environ['PATH']}"
    return str(script)


def test_retail_recalculation_runs_the_engine_twice_and_keeps_provenance(fake_simc):
    ad = WowAdapter(engine=SimcEngine(binary=fake_simc, iterations=7))
    assert ad.capabilities().recalculate_modified is True
    v = ad.recalculate(
        RETAIL, [Modification(kind="profile.set", payload={"key": "level", "value": 70})]
    )
    base = v.baseline.metric(MetricKey.DPS_TOTAL.value)
    var = v.snapshot.metric(MetricKey.DPS_TOTAL.value)
    assert base.value == 80000.5 and var.value == 70000.5
    for m in (base, var):
        assert m.provenance.status == "calculated"
        assert m.provenance.engine == "SimulationCraft" and m.provenance.engine_version == "1130-01"
        assert m.provenance.context["iterations"] == 7
    assert var.provenance.context["modifications_applied"][0]["payload"] == {
        "key": "level",
        "value": 70,
    }
    assert v.snapshot.character.level == 70
    assert v.snapshot.metric(MetricKey.DTPS_TOTAL.value).value == 4200.0


def test_unsupported_modification_is_refused_not_ignored(fake_simc):
    ad = WowAdapter(engine=SimcEngine(binary=fake_simc))
    with pytest.raises(InvalidModification):
        ad.recalculate(RETAIL, [Modification(kind="tree.deallocate", payload={"node_id": 1})])


def test_common_domain_untouched_by_the_new_games():
    """SPEC § 8 metric: adding a game changes GameId (and MetricKey when it measures new things),
    nothing else in the common domain. Proven by the domain isolation test plus this smoke check."""
    from app.domain import build

    assert (
        "wow"
        not in Path(build.__file__)
        .read_text()
        .replace('WOW = "wow"', "")
        .replace('WOW_CLASSIC = "wow_classic"', "")
        .lower()
    )
