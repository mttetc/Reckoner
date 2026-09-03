import pytest

from app.domain.build import GameId
from app.domain.errors import EngineUnavailable, InvalidBuildCode, UnsupportedGame
from app.domain.provenance import MetricKey
from app.games import detect_adapter, get_adapter, list_adapters
from app.games.base import GameAdapter


def test_registry():
    assert [a.game for a in list_adapters()] == [GameId.POE]
    assert isinstance(get_adapter("poe"), GameAdapter)
    with pytest.raises(UnsupportedGame):
        get_adapter("poe2")
    with pytest.raises(UnsupportedGame):
        get_adapter("nope")


def test_detect(code_modern):
    assert detect_adapter(code_modern).game is GameId.POE
    with pytest.raises(InvalidBuildCode):
        detect_adapter("make it tankier")


def test_every_metric_has_provenance_or_reason(code_modern, code_legacy, code_scion):
    adapter = get_adapter("poe")
    for code in (code_modern, code_legacy, code_scion):
        snap = adapter.parse_build(code)
        assert snap.metrics
        for m in snap.metrics:
            if m.known:
                p = m.provenance
                assert p is not None
                assert p.game == "poe"
                assert p.engine == "Path of Building"
                assert p.engine_version is None  # never invented
                assert p.snapshot_id == str(snap.id)
            else:
                assert m.unknown_reason


def test_modern_snapshot_values(code_modern):
    snap = get_adapter("poe").parse_build(code_modern)
    assert snap.game_version == "3.27"
    assert snap.character.subclass == "Slayer"
    assert snap.main_skill == "Vaal Lightning Strike"
    assert snap.metric(MetricKey.DPS_TOTAL).value == pytest.approx(18619973.8, rel=1e-6)
    assert snap.metric(MetricKey.LIFE_MAX).value == 3120
    assert snap.metric(MetricKey.EHP_TOTAL).known
    assert len(snap.tree.node_ids) == 129 and snap.tree.version == "3.27"
    assert snap.items and any(i.slot == "Body Armour" for i in snap.items)
    assert snap.raw.kind == "pob_code" and len(snap.raw.sha256) == 64
    assert "poe.pob_stats" in snap.extra


def test_legacy_snapshot_unknowns_are_explicit(code_legacy):
    snap = get_adapter("poe").parse_build(code_legacy)
    assert snap.game_version is None  # legacy export embeds no tree version
    ehp = snap.metric(MetricKey.EHP_TOTAL)
    assert not ehp.known and "not present" in ehp.unknown_reason
    assert len(snap.tree.node_ids) > 100  # recovered from URL
    assert snap.tree.unknown_reason is None


def test_recalculate_refuses_to_approximate_without_engine(code_modern):
    from app.domain.build import Modification
    from app.games.poe.adapter import PoEAdapter
    from app.games.poe.engine import PobHeadless

    adapter = PoEAdapter(engine=PobHeadless(pob_src=None))
    assert adapter.capabilities().recalculate_modified is False
    with pytest.raises(EngineUnavailable):
        adapter.recalculate(
            code_modern, [Modification(kind="tree.deallocate", payload={"node_id": 41119})]
        )
