"""Stored conversations: list, create, rename, archive, messages."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.engine import get_session
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    app.dependency_overrides.clear()


async def test_thread_lifecycle(client):
    async with client as c:
        r = await c.post("/api/v1/threads")
        assert r.status_code == 201
        tid = r.json()["id"]
        assert r.json()["title"] is None

        user = {
            "id": "m1",
            "role": "user",
            "content": [
                {"type": "text", "text": "Find me a tanky Duelist build " + "eN" + "x" * 240}
            ],
        }
        r = await c.post(
            f"/api/v1/threads/{tid}/messages", json={"message": user, "parent_id": None}
        )
        assert r.status_code == 201 and r.json()["id"] == "m1"
        # Title derived from the first user message, without the pasted code.
        r = await c.get(f"/api/v1/threads/{tid}")
        assert r.json()["title"] == "Find me a tanky Duelist build"

        assistant = {"id": "m2", "role": "assistant", "content": [{"type": "text", "text": "Here"}]}
        await c.post(
            f"/api/v1/threads/{tid}/messages", json={"message": assistant, "parent_id": "m1"}
        )
        r = await c.get(f"/api/v1/threads/{tid}/messages")
        assert [m["id"] for m in r.json()] == ["m1", "m2"]
        assert r.json()[1]["parent_id"] == "m1"

        # Re-sending a message id updates it (edits), no duplicate.
        assistant["content"][0]["text"] = "Here, revised"
        await c.post(
            f"/api/v1/threads/{tid}/messages", json={"message": assistant, "parent_id": "m1"}
        )
        r = await c.get(f"/api/v1/threads/{tid}/messages")
        assert (
            len(r.json()) == 2 and r.json()[1]["message"]["content"][0]["text"] == "Here, revised"
        )

        r = await c.patch(f"/api/v1/threads/{tid}", json={"title": "My Slayer"})
        assert r.json()["title"] == "My Slayer"
        r = await c.patch(f"/api/v1/threads/{tid}", json={"status": "archived"})
        assert r.json()["status"] == "archived"
        r = await c.get("/api/v1/threads")
        assert [t["id"] for t in r.json()] == [tid]

        r = await c.delete(f"/api/v1/threads/{tid}")
        assert r.status_code == 204
        assert (await c.get(f"/api/v1/threads/{tid}")).status_code == 404
        assert (await c.get(f"/api/v1/threads/{tid}/messages")).status_code == 404
