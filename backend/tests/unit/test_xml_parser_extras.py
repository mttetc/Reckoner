"""Fields surfaced by the robustness pass over ~40 forum-linked exports (2026-09-03)."""

from app.games.poe.pob import codec
from app.games.poe.pob.xml_parser import parse_xml


def test_active_skill_set_is_honoured_among_many(code_void_sphere):
    e = parse_xml(codec.decode(code_void_sphere))
    # activeSkillSet=2 ("Endgame - 80"); the leveling sets start with Poisonous Concoction.
    assert e.skill_groups[0].gems[0].name == "Void Sphere of Rending"
    assert e.skill_groups[0].include_in_full_dps is True
    assert e.skill_groups[2].gems[0].name == "Withering Step"
    assert e.skill_groups[2].include_in_full_dps is False
    assert e.header.main_socket_group == 3


def test_full_dps_breakdown_rows(code_void_sphere):
    e = parse_xml(codec.decode(code_void_sphere))
    names = [r.name for r in e.full_dps]
    assert names == [
        "Full Poison DPS",
        "Full Culling DPS",
        "Void Sphere of Rending",
        "Shield Charge",
    ]
    assert e.stats["TotalDPS"] == 0
    assert e.stats["FullDPS"] > 19_000_000
    assert all(r.value >= 0 for r in e.full_dps)


def test_minion_stats_are_separate_from_player_stats(code_minions):
    e = parse_xml(codec.decode(code_minions))
    assert e.stats["TotalDPS"] == 0
    assert e.minion_stats["TotalDPS"] > 100_000
    assert e.minion_stats["Life"] == 4285


def test_no_minion_stats_when_no_minions(code_modern):
    e = parse_xml(codec.decode(code_modern))
    assert e.minion_stats == {}


def test_nil_and_item_granted_groups(code_no_total_dps):
    e = parse_xml(codec.decode(code_no_total_dps))
    assert "TotalDPS" not in e.stats
    first = e.skill_groups[0]
    assert first.main_active_skill is None  # "nil"
    assert first.include_in_full_dps is None  # "nil"
    granted = [g for g in e.skill_groups if g.source and g.source.startswith("Item:")]
    assert len(granted) == 3
    assert any(g.label == "On Kill Monster Explosion" for g in e.skill_groups)


def test_every_fixture_parses(all_codes):
    assert len(all_codes) >= 6
    for name, code in all_codes:
        e = parse_xml(codec.decode(code))
        assert e.header.class_name, name
