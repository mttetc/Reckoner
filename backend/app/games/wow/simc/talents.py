"""Talents as SimulationCraft reports them — never decoded here.

Two engine outputs are read, both text SimulationCraft itself produces:

* the ``Talent Tables`` of its HTML report: the loadout string decoded by the engine into
  class / specialisation / hero tables with row, column, rank and spell id;
* ``spell_query=talent.class=<class>``: every talent node of a class with its position, so the
  whole grid can be drawn and the chosen ones highlighted.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

TREE_KINDS = ("class", "spec", "hero")


@dataclass(frozen=True)
class Talent:
    name: str
    rank: int
    row: int
    col: int
    spell_id: int
    partial: bool  # fewer ranks than the node allows


@dataclass(frozen=True)
class TalentTable:
    title: str  # "Warrior", "Fury", "Slayer" — SimulationCraft's own titles
    kind: str  # class | spec | hero
    points: int
    columns: int
    talents: tuple[Talent, ...]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "kind": self.kind,
            "points": self.points,
            "columns": self.columns,
            "talents": [t.__dict__ for t in self.talents],
        }


_TABLE_RE = re.compile(
    r'<table class="sc talents"><tr><th></th><th colspan="(\d+)">(.*?) Talents \[(\d+)\]</th></tr>'
    r"(.*?)</table>",
    re.S,
)
_ROW_RE = re.compile(r'<tr><th class="right">(\d+)</th>(.*?)(?=<tr><th class="right">|$)', re.S)
_CELL_RE = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)
_LINK_RE = re.compile(r"spell=(\d+)[^>]*>([^<]+)</a>\s*\[(\d+)\](<b>\*</b>)?")


def parse_talent_tables(report_html: str) -> tuple[TalentTable, ...]:
    """The engine prints the class table first, the specialisation second, hero trees after."""
    out: list[TalentTable] = []
    for index, (cols, title, points, body) in enumerate(_TABLE_RE.findall(report_html)):
        talents: list[Talent] = []
        for row_s, cells in _ROW_RE.findall(body):
            row, col = int(row_s), 0
            for attrs, inner in _CELL_RE.findall(cells):
                span = re.search(r'colspan="(\d+)"', attrs)
                width = int(span.group(1)) if span else 1
                link = _LINK_RE.search(inner)
                if link:  # a spanning cell sits in the middle of its span (hero tree apex)
                    talents.append(_talent(link, row, col + (width - 1) // 2))
                col += width
        out.append(
            TalentTable(
                title=html.unescape(title).strip(),
                kind=TREE_KINDS[min(index, 2)],
                points=int(points),
                columns=int(cols),
                talents=tuple(talents),
            )
        )
    return tuple(out)


def _talent(link: re.Match[str], row: int, col: int) -> Talent:
    return Talent(
        name=html.unescape(link.group(2)).strip(),
        rank=int(link.group(3)),
        row=row,
        col=col + 1,  # 1-based like spell_query's "Column"
        spell_id=int(link.group(1)),
        partial=link.group(4) is not None,
    )


@dataclass(frozen=True)
class TalentNode:
    """One entry of ``spell_query=talent.class=…``. Choice nodes share a ``node`` id."""

    name: str
    entry: int
    node: int
    tree: str  # class | spec | hero | selection
    specs: tuple[str, ...]  # empty = every specialisation of the class
    row: int
    col: int
    max_rank: int
    spell_id: int
    subtree: int
    selection_index: int


_FIELD_RE = re.compile(r"^([A-Za-z. ]+?)\s*:\s*(.*)$", re.M)


def parse_spell_query(text: str) -> tuple[TalentNode, ...]:
    nodes: list[TalentNode] = []
    for block in re.split(r"\n(?=Name\s+:)", text):
        if not block.startswith("Name"):
            continue
        f = {k.strip(): v.strip() for k, v in _FIELD_RE.findall(block)}
        if "Tree" not in f or "Node" not in f:
            continue
        tree = f["Tree"].split(" ")[0]
        specs = tuple(
            s.strip().split(" ")[0].lower() for s in f.get("Spec", "").split(",") if s.strip()
        )
        nodes.append(
            TalentNode(
                name=f.get("Name", ""),
                entry=_int(f.get("Entry")),
                node=_int(f.get("Node")),
                tree=tree,
                specs=specs,
                row=_int(f.get("Row")),
                col=_int(f.get("Column")),
                max_rank=_int(f.get("Max Rank"), 1),
                spell_id=_int(f.get("Spell")),
                subtree=_int(f.get("Subtree")),
                selection_index=_int(f.get("Sel. Index")),
            )
        )
    return tuple(nodes)


def _int(v: str | None, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


def talent_grid(nodes: tuple[TalentNode, ...], class_name: str, spec: str) -> dict:
    """Every node of the class, specialisation and hero trees a specialisation can reach, grouped by
    node (choice nodes carry several options). Positions are SimulationCraft's row/column."""
    spec = spec.lower()

    def tree(kind: str, subset: list[TalentNode], subtree: int | None) -> dict:
        by_node: dict[int, list[TalentNode]] = {}
        for n in subset:
            by_node.setdefault(n.node, []).append(n)
        grid_nodes = []
        for node_id, entries in by_node.items():
            entries.sort(key=lambda e: e.selection_index)
            first = entries[0]
            grid_nodes.append(
                {
                    "node": node_id,
                    "row": first.row,
                    "col": first.col,
                    "max_rank": first.max_rank,
                    "choices": [{"name": e.name, "spell_id": e.spell_id} for e in entries],
                }
            )
        grid_nodes.sort(key=lambda g: (g["row"], g["col"]))
        return {
            "kind": kind,
            "subtree": subtree,
            "rows": max((g["row"] for g in grid_nodes), default=0),
            "columns": max((g["col"] for g in grid_nodes), default=0),
            "nodes": grid_nodes,
        }

    class_nodes = [n for n in nodes if n.tree == "class" and (not n.specs or spec in n.specs)]
    spec_nodes = [n for n in nodes if n.tree == "spec" and spec in n.specs]
    hero: dict[int, list[TalentNode]] = {}
    for n in nodes:
        if n.tree == "hero" and spec in n.specs:
            hero.setdefault(n.subtree, []).append(n)
    trees = [tree("class", class_nodes, None), tree("spec", spec_nodes, None)]
    trees += [tree("hero", subset, subtree) for subtree, subset in sorted(hero.items())]
    return {"class_name": class_name.lower(), "spec": spec, "trees": trees}
