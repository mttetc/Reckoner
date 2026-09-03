"""PoB writes ``inf`` for TotalEHP on some builds (seen in a real 3.28 Occultist export)."""

import json

from app.domain.provenance import MetricKey
from app.games.poe.adapter import PoEAdapter
from app.games.poe.pob import codec
from app.games.poe.pob.xml_parser import parse_xml


def _with_inf_ehp(code: str) -> str:
    xml = codec.decode(code).decode()
    assert 'stat="TotalEHP"' in xml
    import re

    # attribute order varies between exports; cover both
    xml = re.sub(r'(<PlayerStat stat="TotalEHP" value=")[^"]+(")', r"\1inf\2", xml)
    xml = re.sub(r'(<PlayerStat value=")[^"]+(" stat="TotalEHP")', r"\1inf\2", xml)
    assert 'value="inf"' in xml
    return codec.encode(xml.encode())


def test_parser_reports_non_finite_rows_separately(code_modern):
    e = parse_xml(codec.decode(_with_inf_ehp(code_modern)))
    assert "TotalEHP" not in e.stats
    assert "TotalEHP" in e.non_finite_stats


def test_metric_is_unknown_with_reason_and_snapshot_is_json_safe(code_modern):
    s = PoEAdapter().parse_build(_with_inf_ehp(code_modern))
    m = s.metric(MetricKey.EHP_TOTAL)
    assert m.value is None
    assert "non-finite" in m.unknown_reason

    def reject(constant: str) -> None:  # json.loads accepts Infinity/NaN by default; we must not
        raise AssertionError(f"non-finite token {constant!r} in serialised snapshot")

    json.loads(s.model_dump_json(), parse_constant=reject)
    json.dumps(s.model_dump(mode="json"), allow_nan=False)  # what the DB layer relies on
