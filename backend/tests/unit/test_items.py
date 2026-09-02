from app.games.poe.pob.items import parse_item_text

RARE = """Rarity: RARE
Storm Circle
Two-Stone Ring
Item Level: 83
LevelReq: 64
Implicits: 1
+16% to Fire and Lightning Resistances
+31 to maximum Mana"""


def test_rare_item():
    it = parse_item_text(RARE, "Ring 1")
    assert (it.rarity, it.name, it.base_type, it.item_level, it.slot) == (
        "RARE",
        "Storm Circle",
        "Two-Stone Ring",
        83,
        "Ring 1",
    )
    assert it.lines[-1] == "+31 to maximum Mana"


def test_magic_item_has_no_name():
    it = parse_item_text("Rarity: MAGIC\nSapphire Flask of Warding\nQuality: 20", "Flask 1")
    assert it.name is None and it.base_type == "Sapphire Flask of Warding" and it.rarity == "MAGIC"


def test_empty_text():
    it = parse_item_text("", None)
    assert it.name is None and it.lines == ()
