"""Tree geometry comes from PoB itself (positions, links, classes), never re-derived."""

import pytest
from fastapi.testclient import TestClient

from app.games.poe.adapter import PoEAdapter
from app.games.poe.engine import get_engine
from app.main import app

pytestmark = pytest.mark.skipif(
    not get_engine().available(), reason="headless PoB not installed (RECKONER_POB_SRC)"
)


def test_geometry_covers_the_fixture_tree(code_modern):
    ad = PoEAdapter()
    snap = ad.parse_build(code_modern)
    geo = ad.tree_geometry(snap.game_version)
    ids = {n["id"] for n in geo["nodes"]}
    # Cluster-jewel nodes (ids >= 65536) exist only inside a build's own graph; the static tree
    # cannot contain them and the UI says how many it did not draw.
    static_alloc = {i for i in snap.tree.node_ids if i < 65536}
    cluster_alloc = {i for i in snap.tree.node_ids if i >= 65536}
    assert static_alloc <= ids, "every non-cluster allocated node must be drawable"
    assert cluster_alloc, "the fixture does use cluster jewels"
    by_id = {n["id"]: n for n in geo["nodes"]}
    lethality = by_id[41119]
    assert lethality["name"] == "Lethality" and lethality["type"] == "Notable"
    assert isinstance(lethality["x"], int) and isinstance(lethality["y"], int)
    assert lethality["linked"], "nodes must carry their neighbours"
    assert all(other in ids for other in lethality["linked"])
    assert sum(len(n["linked"]) for n in geo["nodes"]) > 4000
    assert sum(1 for n in geo["nodes"] if n["type"] == "ClassStart") == 7
    assert len(geo["classes"]) >= 6 and any(c["name"] == "Duelist" for c in geo["classes"])
    assert len(geo["orbit_radii"]) >= 5 and geo["groups"]


def test_geometry_is_cached_and_versioned():
    eng = get_engine()
    a = eng.tree_geometry("3.29")
    b = eng.tree_geometry("3_29")
    assert a is b and a["version"] == "3_29"


def test_api_tree_endpoint(code_modern):
    c = TestClient(app)
    r = c.get("/api/v1/games/poe/tree/3.27")
    assert r.status_code == 200
    assert r.json()["version"] == "3_27" and len(r.json()["nodes"]) > 1000
    r = c.get("/api/v1/games/poe/tree/9.99")
    assert r.status_code == 422
    r = c.get("/api/v1/games/poe2/tree/0.5")
    assert r.status_code == 404
