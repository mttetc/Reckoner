"""Adapter behaviour on the awkward-but-real exports found in the robustness pass."""

from app.domain.provenance import MetricKey
from app.games.poe.adapter import PoEAdapter

ad = PoEAdapter()


def test_main_skill_is_the_export_selection_even_if_utility(code_void_sphere):
    s = ad.parse_build(code_void_sphere)
    # The author left Withering Step selected; PoB's TotalDPS is therefore 0. We do not guess
    # a "better" main skill — we report the selection and say where it came from.
    assert s.main_skill == "Withering Step"
    total = s.metric(MetricKey.DPS_TOTAL)
    assert total.value == 0
    assert total.provenance.context["main_skill_source"] == "socket group selected in the export"


def test_full_dps_provenance_lists_what_it_aggregates(code_void_sphere):
    s = ad.parse_build(code_void_sphere)
    full = s.metric(MetricKey.DPS_FULL)
    assert full.value > 19_000_000
    assert full.provenance.context["aggregates"] == [
        "Full Poison DPS",
        "Full Culling DPS",
        "Void Sphere of Rending",
        "Shield Charge",
    ]
    assert len(s.extra["poe.full_dps_breakdown"]) == 4


def test_minion_metrics_emitted_only_when_present(code_minions, code_modern):
    with_minions = ad.parse_build(code_minions)
    m = with_minions.metric(MetricKey.MINION_DPS_TOTAL)
    assert m is not None and m.value > 100_000
    assert m.provenance.status == "calculated"
    assert with_minions.metric(MetricKey.MINION_LIFE_MAX).value == 4285

    without = ad.parse_build(code_modern)
    assert without.metric(MetricKey.MINION_DPS_TOTAL) is None
    assert without.extra["poe.pob_minion_stats"] == {}


def test_missing_total_dps_is_unknown_not_zero(code_no_total_dps):
    s = ad.parse_build(code_no_total_dps)
    total = s.metric(MetricKey.DPS_TOTAL)
    assert total.value is None
    assert "not present" in total.unknown_reason
    assert s.main_skill == "Artillery Ballista of Cross Strafe"
    assert s.character.subclass == "Chieftain"


def test_every_fixture_yields_a_snapshot_with_provenance(all_codes):
    for name, code in all_codes:
        s = ad.parse_build(code)
        assert s.character.class_name, name
        for m in s.metrics:
            assert (m.value is None) != (m.provenance is not None), (name, m.key)
