"""What the analyze tool hands to the model: every talent by name, so none is ever invented."""

from pathlib import Path

from app.agent.tools import compact_snapshot
from app.games.wow_classic.adapter import WowClassicAdapter
from app.games.wow_classic.wowsims.data import WowSimsData
from app.games.wow_classic.wowsims.engine import WowSimsEngine

FIX = Path(__file__).parents[1] / "fixtures" / "wow"


def test_compact_snapshot_names_every_talent_group(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "wowsims_bin", None)
    ad = WowClassicAdapter(
        engine=WowSimsEngine(binary=None), data=WowSimsData(FIX / "wowsims_data")
    )
    view = compact_snapshot(
        ad.parse_build((FIX / "wowsims_fury_warrior_settings.json").read_text())
    )
    groups = {g["group"]: g["names"] for g in view["skills"]}
    assert set(groups) == {"Arms talents", "Fury talents"}
    assert "Cruelty (5)" in groups["Fury talents"]
    assert view["main_skill"] is None and "no main-skill selection" in view["main_skill_note"]
    assert "Lionheart Helm" in view["items"]
