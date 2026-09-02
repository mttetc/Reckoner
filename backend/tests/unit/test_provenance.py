import pytest
from pydantic import ValidationError

from app.domain.provenance import Metric, Provenance, ProvenanceStatus


def _prov(**kw) -> Provenance:
    base = dict(status=ProvenanceStatus.CALCULATED, source="test", game="poe")
    base.update(kw)
    return Provenance(**base)


def test_bare_number_is_rejected():
    with pytest.raises(ValidationError, match="bare number"):
        Metric(key="dps.total", value=91.4e6)


def test_unknown_requires_reason():
    with pytest.raises(ValidationError, match="no reason"):
        Metric(key="dps.total")
    m = Metric.unknown("dps.total", "engine unavailable")
    assert not m.known and m.value is None


def test_known_with_provenance():
    m = Metric(key="life.max", value=6911, provenance=_prov())
    assert m.known and m.provenance.status is ProvenanceStatus.CALCULATED


def test_estimated_requires_methodology():
    with pytest.raises(ValidationError, match="methodology"):
        _prov(status=ProvenanceStatus.ESTIMATED)
    _prov(status=ProvenanceStatus.ESTIMATED, methodology="median of n=412 observed clears")


def test_metrics_are_immutable():
    m = Metric(key="life.max", value=1, provenance=_prov())
    with pytest.raises(ValidationError):
        m.value = 2  # type: ignore[misc]
