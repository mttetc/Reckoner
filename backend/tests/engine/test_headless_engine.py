"""Headless Path of Building engine (SPEC § 5 B).

These tests need a PoB checkout (scripts/install_pob.sh) and luajit; they skip otherwise and the
CI `engine` job runs them for real. Every number asserted here comes from PoB — we only check
directions, invariants and provenance, never a hand-derived value.
"""

import pytest

from app.domain.build import Modification
from app.domain.errors import InvalidModification
from app.domain.provenance import MetricKey
from app.games.poe.adapter import SOURCE_HEADLESS, PoEAdapter
from app.games.poe.engine import get_engine

pytestmark = pytest.mark.skipif(
    not get_engine().available(), reason="headless PoB not installed (RECKONER_POB_SRC)"
)

LETHALITY = 41119  # a notable that is a leaf in the slayer fixture's tree


@pytest.fixture(scope="module")
def adapter() -> PoEAdapter:
    return PoEAdapter()


def _dps(snapshot) -> float:
    return snapshot.metric(MetricKey.DPS_TOTAL).value


def test_engine_reports_its_version():
    info = get_engine().info()
    assert info.engine == "Path of Building"
    assert info.engine_version and info.engine_version[0].isdigit()
    assert "tree.deallocate" in info.modification_kinds


def test_capability_is_true_when_engine_installed(adapter):
    assert adapter.capabilities().recalculate_modified is True


def test_baseline_is_same_engine_and_close_to_export(adapter, code_modern):
    variant = adapter.recalculate(
        code_modern, [Modification(kind="tree.deallocate", payload={"node_id": LETHALITY})]
    )
    parent = adapter.parse_build(code_modern)
    base = variant.baseline
    assert base is not None
    # Sanity, not correctness: the export was produced by another PoB version on 3.27 data, our
    # engine runs current data. Small drift is expected; a large one would mean a broken load.
    assert abs(_dps(base) - _dps(parent)) / _dps(parent) < 0.05
    assert (
        abs(base.metric(MetricKey.LIFE_MAX).value - parent.metric(MetricKey.LIFE_MAX).value) < 100
    )
    assert base.tree.node_ids == parent.tree.node_ids


def test_deallocate_leaf_lowers_dps_and_reallocating_restores_it_exactly(adapter, code_modern):
    dealloc = Modification(kind="tree.deallocate", payload={"node_id": LETHALITY})
    alloc = Modification(kind="tree.allocate", payload={"node_id": LETHALITY})

    v1 = adapter.recalculate(code_modern, [dealloc])
    assert _dps(v1.snapshot) < _dps(v1.baseline)
    assert LETHALITY in v1.baseline.tree.node_ids
    assert LETHALITY not in v1.snapshot.tree.node_ids
    assert len(v1.snapshot.tree.node_ids) == len(v1.baseline.tree.node_ids) - 1

    v2 = adapter.recalculate(code_modern, [dealloc, alloc])
    assert _dps(v2.snapshot) == _dps(v2.baseline)
    assert set(v2.snapshot.tree.node_ids) == set(v2.baseline.tree.node_ids)


def test_config_set_is_validated_and_effective(adapter, code_modern):
    none = adapter.recalculate(
        code_modern,
        [Modification(kind="config.set", payload={"name": "enemyIsBoss", "value": "None"})],
    )
    uber = adapter.recalculate(
        code_modern,
        [Modification(kind="config.set", payload={"name": "enemyIsBoss", "value": "uber"})],
    )
    assert _dps(none.snapshot) > _dps(uber.snapshot)
    applied = uber.snapshot.metric(MetricKey.DPS_TOTAL).provenance.context["modifications_applied"]
    assert applied[0]["value"] == "Uber"  # canonicalised, case-insensitive input
    assert applied[0]["previous"] == "Pinnacle"


def test_gem_level_change(adapter, code_modern):
    v = adapter.recalculate(
        code_modern,
        [Modification(kind="gem.set_level", payload={"gem": "Vaal Lightning Strike", "level": 21})],
    )
    assert _dps(v.snapshot) > _dps(v.baseline)
    main = next(
        g for grp in v.snapshot.skills for g in grp.gems if g.name == "Vaal Lightning Strike"
    )
    assert main.level == 21


def test_engine_metrics_carry_engine_provenance(adapter, code_modern):
    v = adapter.recalculate(
        code_modern, [Modification(kind="tree.deallocate", payload={"node_id": LETHALITY})]
    )
    for snap in (v.baseline, v.snapshot):
        for m in snap.metrics:
            if m.value is None:
                assert m.unknown_reason
                continue
            p = m.provenance
            assert p.source == SOURCE_HEADLESS
            assert p.engine_version
            assert p.status == "calculated"
            assert "engine_data_version" in p.context
    assert (
        v.snapshot.metric(MetricKey.DPS_TOTAL).provenance.context["modifications_applied"][0][
            "name"
        ]
        == "Lethality"
    )
    assert v.baseline.metric(MetricKey.DPS_TOTAL).provenance.context["modifications_applied"] == []


@pytest.mark.parametrize(
    "mod, fragment",
    [
        (Modification(kind="tree.deallocate", payload={"node_id": 1}), "unknown passive node"),
        (Modification(kind="tree.allocate", payload={"node_id": 1}), "unknown passive node"),
        (
            Modification(kind="config.set", payload={"name": "enemyIsBoss", "value": "Godlike"}),
            "not a valid value",
        ),
        (Modification(kind="config.set", payload={"name": "nope", "value": 1}), "unknown config"),
        (Modification(kind="item.replace", payload={}), "unsupported kind"),
        (Modification(kind="gem.set_level", payload={"gem": "Nope", "level": 5}), "not found"),
    ],
)
def test_refused_modifications_are_explicit(adapter, code_modern, mod, fragment):
    with pytest.raises(InvalidModification) as exc:
        adapter.recalculate(code_modern, [mod])
    assert fragment in str(exc.value)


def test_engine_survives_a_refused_modification(adapter, code_modern):
    with pytest.raises(InvalidModification):
        adapter.recalculate(
            code_modern, [Modification(kind="tree.deallocate", payload={"node_id": 1})]
        )
    v = adapter.recalculate(
        code_modern, [Modification(kind="tree.deallocate", payload={"node_id": LETHALITY})]
    )
    assert _dps(v.snapshot) > 0
