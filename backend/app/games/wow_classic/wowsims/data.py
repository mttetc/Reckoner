"""WoWSims' own data files, read from its checkout: the item database (names, item levels) and the
Classic talent trees (names and positions). Both are the simulator's — we only look things up."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def field_to_name(field: str) -> str:
    """'improvedHeroicStrike' → 'Improved Heroic Strike' (the tree files carry field names)."""
    return " ".join(w[:1].upper() + w[1:] for w in _CAMEL.split(field) if w)


@dataclass(frozen=True)
class ClassicTalent:
    name: str
    rank: int
    max_rank: int
    row: int  # 1-based
    col: int  # 1-based
    index: int  # position in the tree, i.e. the digit's index in the talent string
    node_id: int  # stable synthetic id: tree_index * 1000 + index + 1


@dataclass(frozen=True)
class ClassicTree:
    name: str  # "Arms", "Fury", "Protection"
    index: int
    points: int
    rows: int
    columns: int
    talents: tuple[ClassicTalent, ...]  # every talent of the tree; rank 0 = not taken

    def to_table(self) -> dict:
        """The shape the build card's talent grid reads (taken talents only)."""
        return {
            "title": self.name,
            "kind": self.name.lower(),
            "points": self.points,
            "columns": self.columns,
            "talents": [
                {
                    "name": t.name,
                    "rank": t.rank,
                    "row": t.row,
                    "col": t.col,
                    "spell_id": t.node_id,
                    "partial": t.rank < t.max_rank,
                }
                for t in self.talents
                if t.rank > 0
            ],
        }


class WowSimsData:
    def __init__(self, root: Path | None) -> None:
        self.root = root
        self._items: dict[int, dict] | None = None
        self._trees: dict[str, list[dict] | None] = {}

    @classmethod
    def locate(cls, binary: str | None) -> WowSimsData:
        """Next to the CLI (``<checkout>/build/wowsimcli``) or at RECKONER_WOWSIMS_SRC."""
        candidates = []
        if settings.wowsims_src:
            candidates.append(Path(settings.wowsims_src))
        if binary:
            candidates.append(Path(binary).resolve().parents[1])
        for root in candidates:
            if (root / "assets" / "database" / "db.json").exists():
                return cls(root)
        return cls(None)

    def available(self) -> bool:
        return self.root is not None

    def item(self, item_id: int) -> dict | None:
        if self.root is None:
            return None
        if self._items is None:
            db = json.loads((self.root / "assets" / "database" / "db.json").read_text())
            self._items = {it["id"]: it for it in db.get("items", []) if "id" in it}
        return self._items.get(item_id)

    def trees(self, class_name: str) -> list[dict] | None:
        key = class_name.lower().replace(" ", "")
        if self.root is None:
            return None
        if key not in self._trees:
            path = self.root / "ui" / "core" / "talents" / "trees" / f"{key}.json"
            self._trees[key] = json.loads(path.read_text()) if path.exists() else None
        return self._trees[key]

    def decode_talents(self, class_name: str, talents_string: str | None) -> list[ClassicTree]:
        """Digits per talent, trees separated by '-', trailing zeros omitted — WoWSims' format."""
        trees = self.trees(class_name)
        if not trees:
            return []
        parts = ((talents_string or "").split("-") + ["", "", ""])[:3]
        out: list[ClassicTree] = []
        for ti, tree in enumerate(trees):
            digits = parts[ti] if ti < len(parts) else ""
            talents = []
            for i, t in enumerate(tree.get("talents", [])):
                rank = int(digits[i]) if i < len(digits) and digits[i].isdigit() else 0
                loc = t.get("location", {})
                talents.append(
                    ClassicTalent(
                        name=field_to_name(t.get("fieldName", f"talent{i}")),
                        rank=rank,
                        max_rank=int(t.get("maxPoints", 1)),
                        row=int(loc.get("rowIdx", 0)) + 1,
                        col=int(loc.get("colIdx", 0)) + 1,
                        index=i,
                        node_id=ti * 1000 + i + 1,
                    )
                )
            out.append(
                ClassicTree(
                    name=str(tree.get("name") or f"Tree {ti + 1}"),
                    index=ti,
                    points=sum(t.rank for t in talents),
                    rows=max((t.row for t in talents), default=0),
                    columns=max((t.col for t in talents), default=0),
                    talents=tuple(talents),
                )
            )
        return out
