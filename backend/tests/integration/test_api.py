from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_games_lists_capabilities_honestly():
    r = client.get("/api/v1/games")
    assert r.status_code == 200
    [poe] = r.json()
    assert poe["id"] == "poe"
    assert poe["capabilities"]["analyze_existing"] is True
    assert poe["capabilities"]["recalculate_modified"] is False


def test_analyze_modern(code_modern):
    r = client.post("/api/v1/builds/analyze", json={"code": code_modern})
    assert r.status_code == 200, r.text
    snap = r.json()["snapshot"]
    assert snap["game"] == "poe" and snap["game_version"] == "3.27"
    dps = next(m for m in snap["metrics"] if m["key"] == "dps.total")
    assert dps["value"] > 1e7
    assert dps["provenance"]["status"] == "calculated"
    assert dps["provenance"]["engine"] == "Path of Building"
    # No number without provenance in the whole response
    for m in snap["metrics"]:
        assert (m["value"] is None) != (m["provenance"] is not None)


def test_analyze_forced_game(code_legacy):
    r = client.post("/api/v1/builds/analyze", json={"code": code_legacy, "game": "poe"})
    assert r.status_code == 200
    assert r.json()["snapshot"]["game_version"] is None


def test_analyze_invalid_code():
    r = client.post("/api/v1/builds/analyze", json={"code": "this is not a build code"})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_build_code"


def test_analyze_unsupported_game(code_modern):
    r = client.post("/api/v1/builds/analyze", json={"code": code_modern, "game": "poe2"})
    # GameId accepts poe2 (Phase 2) but no adapter is registered yet → explicit 404, not a guess.
    assert r.status_code == 404
    assert r.json()["code"] == "unsupported_game"
