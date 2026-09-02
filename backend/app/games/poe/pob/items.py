"""Minimal reading of PoB item text. Only structure, never stat interpretation."""

from __future__ import annotations

from app.domain.build import Item

_HEADER_KEYS = ("Unique ID:", "Item Level:", "Quality:", "Sockets:", "LevelReq:", "Implicits:")


def parse_item_text(text: str, slot: str | None) -> Item:
    lines = tuple(ln.strip() for ln in text.splitlines() if ln.strip())
    rarity = name = base = None
    item_level = None
    if lines and lines[0].lower().startswith("rarity:"):
        rarity = lines[0].split(":", 1)[1].strip().upper()
        body = lines[1:]
    else:
        body = lines
    if rarity in ("RARE", "UNIQUE", "RELIC"):
        name = body[0] if len(body) > 0 else None
        base = body[1] if len(body) > 1 else None
    else:
        base = body[0] if body else None
    for ln in lines:
        if ln.startswith("Item Level:"):
            try:
                item_level = int(ln.split(":", 1)[1])
            except ValueError:
                pass
    return Item(
        slot=slot, name=name, base_type=base, rarity=rarity, item_level=item_level, lines=lines
    )
