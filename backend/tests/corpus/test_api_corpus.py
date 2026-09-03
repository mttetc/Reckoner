import pytest
from httpx import ASGITransport, AsyncClient

from app.corpus.pipeline import FetchedCode, ingest_many
from app.db.engine import get_session
from app.db.repository import SourceRef
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


async def test_empty_corpus_is_an_honest_empty_answer(client, session):
    async with client as c:
        r = await c.get("/api/v1/builds?game=poe")
        assert r.status_code == 200
        assert r.json() == {"total": 0, "items": []}
        r = await c.get("/api/v1/corpus/stats")
        assert r.json()["snapshots"] == 0


async def test_search_and_detail(client, session, all_codes):
    await ingest_many(
        session,
        [
            FetchedCode(
                c,
                SourceRef(
                    kind="paste",
                    url=f"https://pobb.in/{n}",
                    game="poe",
                    title=n,
                    parent_url="https://www.pathofexile.com/forum/view-thread/42",
                    terms="test",
                ),
            )
            for n, c in all_codes
        ],
    )
    async with client as c:
        r = await c.get("/api/v1/builds", params={"game": "poe", "class_name": "Duelist"})
        body = r.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["main_skill"] == "Vaal Lightning Strike"
        assert item["source"]["parent_url"].endswith("/view-thread/42")
        for m in item["metrics"]:
            assert (m["value"] is None) != (m["provenance"] is not None)

        r = await c.get(f"/api/v1/builds/{item['snapshot_id']}")
        assert r.status_code == 200
        assert r.json()["snapshot"]["character"]["subclass"] == "Slayer"
        assert r.json()["source"]["url"].startswith("https://pobb.in/")

        r = await c.get("/api/v1/builds/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

        r = await c.get("/api/v1/builds", params={"sort": "nope"})
        assert r.status_code == 422
