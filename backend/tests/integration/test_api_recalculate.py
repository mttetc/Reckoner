import pytest
from fastapi.testclient import TestClient

from app.domain.build import GameId
from app.games import _ADAPTERS
from app.games.poe.engine import PobHeadless, get_engine
from app.main import app

client = TestClient(app)
MODS = [{"kind": "tree.deallocate", "payload": {"node_id": 41119}}]


def test_recalculate_without_engine_is_503_not_a_guess(code_modern, monkeypatch):
    monkeypatch.setattr(_ADAPTERS[GameId.POE], "_engine", PobHeadless(pob_src=None))
    r = client.post("/api/v1/builds/recalculate", json={"code": code_modern, "modifications": MODS})
    assert r.status_code == 503
    assert r.json()["code"] == "engine_unavailable"
    assert "install_pob" in r.json()["message"]


def test_recalculate_requires_at_least_one_modification(code_modern):
    r = client.post("/api/v1/builds/recalculate", json={"code": code_modern, "modifications": []})
    assert r.status_code == 422


@pytest.mark.skipif(not get_engine().available(), reason="headless PoB not installed")
def test_recalculate_end_to_end(code_modern):
    r = client.post("/api/v1/builds/recalculate", json={"code": code_modern, "modifications": MODS})
    assert r.status_code == 200, r.text
    v = r.json()["variant"]
    assert v["modifications"] == MODS
    dps = lambda s: next(m for m in s["metrics"] if m["key"] == "dps.total")  # noqa: E731
    assert dps(v["snapshot"])["value"] < dps(v["baseline"])["value"]
    assert dps(v["snapshot"])["provenance"]["source"] == "pob:headless"
    assert dps(v["snapshot"])["provenance"]["engine_version"]


@pytest.mark.skipif(not get_engine().available(), reason="headless PoB not installed")
def test_recalculate_refused_modification_is_422(code_modern):
    r = client.post(
        "/api/v1/builds/recalculate",
        json={
            "code": code_modern,
            "modifications": [{"kind": "tree.deallocate", "payload": {"node_id": 1}}],
        },
    )
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_modification"
