"""SSE steps and feedback endpoints (scripted policy, seeded database)."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import get_session
from app.main import app
from tests.corpus.test_agent import _seed

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://t", timeout=60)
    app.dependency_overrides.clear()


async def test_stream_emits_steps_then_done(client, session, all_codes):
    await _seed(session, all_codes)
    events = []
    async with client as c:
        async with c.stream(
            "POST", "/api/v1/ask/stream", json={"question": "Find me a Duelist build"}
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
    kinds = [e["type"] for e in events]
    assert kinds[:2] == ["step_start", "step_end"]
    assert kinds[-1] == "done"
    assert events[0]["tool"] == "search_builds"
    assert events[1]["ok"] is True and "match" in events[1]["summary"]
    done = events[-1]["response"]
    assert "Slayer" in done["answer"]
    assert done["suggestions"] and len(done["suggestions"]) <= 3
    assert done["audit"]["clean"] is True


async def test_feedback_is_stored(client, session):
    async with client as c:
        r = await c.post(
            "/api/v1/feedback",
            json={"message_id": "m1", "rating": "positive", "question": "q", "answer": "a"},
        )
        assert r.status_code == 204
        r = await c.post("/api/v1/feedback", json={"message_id": "m1", "rating": "meh"})
        assert r.status_code == 422
    n = (await session.execute(text("SELECT count(*) FROM answer_feedback"))).scalar_one()
    assert n == 1
