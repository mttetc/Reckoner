"""Talents are read from SimulationCraft's own outputs; both readers agree with each other."""

from pathlib import Path

from app.games.wow.simc.talents import parse_spell_query, parse_talent_tables, talent_grid

FIX = Path(__file__).parents[1] / "fixtures" / "wow"
TABLES = parse_talent_tables((FIX / "simc_fury_talents.html").read_text())
NODES = parse_spell_query((FIX / "simc_spell_query_talent_warrior.txt").read_text())


def test_html_talent_tables_carry_title_kind_points_and_positions():
    assert [(t.title, t.kind, t.points, t.columns) for t in TABLES] == [
        ("Warrior", "class", 34, 7),
        ("Fury", "spec", 34, 7),
        ("Slayer", "hero", 13, 5),
    ]
    warrior = TABLES[0]
    first = warrior.talents[0]
    assert (first.name, first.row, first.col, first.rank, first.spell_id) == (
        "Berserker Stance",
        1,
        2,
        1,
        386196,
    )
    apex = TABLES[2].talents[0]  # the hero tree's single top node spans the table
    assert (apex.name, apex.row, apex.col) == ("Slayer's Dominance", 1, 3)
    assert sum(t.rank for t in TABLES[1].talents) == 34
    assert not any(t.partial for t in TABLES[0].talents)


def test_spell_query_lists_every_warrior_talent_node_with_its_place():
    assert len(NODES) == 247
    battle_stance = next(n for n in NODES if n.name == "Battle Stance")
    assert battle_stance.tree == "class" and battle_stance.specs == ("protection",)
    assert (battle_stance.row, battle_stance.col, battle_stance.spell_id) == (1, 2, 386164)
    choice = [n for n in NODES if n.node == 90450]
    assert sorted(n.name for n in choice) == ["Hunker Down", "Spellbreaker"]


def test_fury_grid_holds_every_talent_the_engine_says_the_build_took():
    grid = talent_grid(NODES, "Warrior", "Fury")
    kinds = [t["kind"] for t in grid["trees"]]
    assert kinds == ["class", "spec", "hero", "hero"]
    class_names = {c["name"] for g in grid["trees"][0]["nodes"] for c in g["choices"]}
    assert "Berserker Stance" in class_names and "Battle Stance" not in class_names
    spell_ids = {c["spell_id"] for t in grid["trees"] for g in t["nodes"] for c in g["choices"]}
    for table in TABLES:
        for talent in table.talents:
            assert talent.spell_id in spell_ids, (table.title, talent.name)
    # Choice nodes keep both options at one place.
    choice = next(g for t in grid["trees"] for g in t["nodes"] if len(g["choices"]) > 1)
    assert len(choice["choices"]) == 2
    assert all(t["rows"] > 0 and t["columns"] > 0 for t in grid["trees"])
