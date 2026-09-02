import pytest

from app.domain.errors import InvalidBuildCode
from app.games.poe.pob import codec
from app.games.poe.pob.xml_parser import parse_xml


def test_modern_layout(code_modern):
    e = parse_xml(codec.decode(code_modern))
    assert e.layout == "modern"
    assert (e.header.class_name, e.header.ascend_class_name, e.header.level) == (
        "Duelist",
        "Slayer",
        95,
    )
    assert e.stats["TotalDPS"] == pytest.approx(18619973.803211)
    assert e.stats["Life"] == 3120
    assert e.spec is not None and e.spec.tree_version == "3_27" and len(e.spec.nodes) == 129
    assert e.spec.mastery_effects  # {node: effect}
    assert e.skill_groups and any(g.gems for g in e.skill_groups)
    assert e.slots  # active ItemSet slots resolved
    assert isinstance(e.config, dict)


def test_legacy_layout(code_legacy):
    e = parse_xml(codec.decode(code_legacy))
    assert e.layout == "legacy"
    assert e.header.class_name == "Witch"
    assert e.stats["TotalDPS"] == pytest.approx(290526.5625)
    assert e.spec is not None and e.spec.tree_version is None and e.spec.nodes == ()
    assert e.spec.url and "passive-skill-tree" in e.spec.url


def test_duplicate_stats_keep_first(code_legacy):
    e = parse_xml(codec.decode(code_legacy))
    assert e.stats["Speed"] == pytest.approx(2.88)


def test_rejects_wrong_root():
    with pytest.raises(InvalidBuildCode, match="root"):
        parse_xml(b"<Something/>")


def test_rejects_missing_build():
    with pytest.raises(InvalidBuildCode, match="Build"):
        parse_xml(b"<PathOfBuilding/>")


def test_rejects_malformed_xml():
    with pytest.raises(InvalidBuildCode, match="malformed"):
        parse_xml(b"<PathOfBuilding><Build></PathOfBuilding>")


def test_entities_are_not_resolved():
    evil = (
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b'<PathOfBuilding><Build className="&xxe;"/></PathOfBuilding>'
    )
    try:
        e = parse_xml(evil)
    except InvalidBuildCode:
        return
    assert not e.header.class_name or "root:" not in e.header.class_name


def test_config_inputs_are_typed():
    xml = (
        b'<PathOfBuilding><Build/><Config activeConfigSet="2">'
        b'<ConfigSet id="1"><Input name="enemyIsBoss" string="None"/></ConfigSet>'
        b'<ConfigSet id="2"><Input name="enemyIsBoss" string="Pinnacle"/>'
        b'<Input name="usePowerCharges" boolean="true"/>'
        b'<Input name="multiplierNearbyEnemies" number="3"/></ConfigSet>'
        b"</Config></PathOfBuilding>"
    )
    e = parse_xml(xml)
    assert e.config == {
        "enemyIsBoss": "Pinnacle",
        "usePowerCharges": True,
        "multiplierNearbyEnemies": 3.0,
    }
