"""SPEC § 6 / § 13.3 — game isolation, automated. Runs against PostgreSQL + pgvector."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from lxml import html

from app.db.engine import get_session
from app.knowledge.chunker import chunk_post, first_post
from app.knowledge.embedder import HashEmbedder
from app.knowledge.ingest import ingest_documents
from app.knowledge.repository import GameFilterMissing, KnowledgeRepository
from app.knowledge.sources.ggg_forum import PatchNoteDocument
from app.main import app

pytestmark = pytest.mark.asyncio
FIX = Path(__file__).parents[1] / "fixtures" / "forum"
EMB = HashEmbedder()


def _doc(game: str, name: str, url: str, title: str, version: str, patch: str) -> PatchNoteDocument:
    post = first_post(html.fromstring((FIX / name).read_text()))
    return PatchNoteDocument(
        game=game,
        source="ggg:patch-notes",
        source_url=url,
        title=title,
        version=version,
        patch=patch,
        published_at=None,
        chunks=chunk_post(post),
    )


POE = _doc(
    "poe",
    "poe1_patch_notes.html",
    "https://www.pathofexile.com/forum/view-thread/1",
    "3.29.0b Patch Notes",
    "3.29.0b",
    "3.29",
)
POE2 = _doc(
    "poe2",
    "poe2_patch_notes.html",
    "https://www.pathofexile.com/forum/view-thread/2",
    "0.5.5 Patch Notes",
    "0.5.5",
    "0.5",
)

QUERIES = [
    "Lightning Strike changes",
    "Herald of Ash reservation for Ranger",
    "Spectral Throw bug fix",
]


async def _seed(session):
    report = await ingest_documents(session, [POE, POE2], embedder=EMB)
    assert report.documents == 2 and report.skipped == []
    return KnowledgeRepository(session, EMB)


async def test_no_cross_game_passage_is_ever_retrieved(session):
    repo = await _seed(session)
    for game, other in (("poe", "poe2"), ("poe2", "poe")):
        for q in QUERIES:
            hits = await repo.search(game, q, k=50)
            assert hits, (game, q)
            assert {h.chunk.metadata.game for h in hits} == {game}, (game, q, other)


async def test_retrieval_without_game_is_refused(session):
    repo = await _seed(session)
    with pytest.raises(GameFilterMissing):
        await repo.search(None, "Lightning Strike")
    with pytest.raises(GameFilterMissing):
        await repo.search("", "Lightning Strike")


async def test_reingest_replaces_instead_of_duplicating(session):
    repo = await _seed(session)
    before = await repo.stats()
    await ingest_documents(session, [POE], embedder=EMB)
    after = await repo.stats()
    assert before == after
    assert after["per_game"] == {"poe": len(POE.chunks), "poe2": len(POE2.chunks)}
    assert after["embedders"] == [EMB.name]


async def test_patch_filter_and_patch_listing(session):
    repo = await _seed(session)
    assert [p["patch"] for p in await repo.patches("poe")] == ["3.29"]
    assert [p["patch"] for p in await repo.patches("poe2")] == ["0.5"]
    assert await repo.search("poe", "Lightning Strike", patch="3.28") == []
    hits = await repo.search("poe", "Lightning Strike", patch="3.29")
    assert hits and all(h.chunk.metadata.patch == "3.29" for h in hits)


async def test_api_requires_game_and_isolates(session, monkeypatch):
    from app.knowledge import embedder as emb_mod

    monkeypatch.setattr(emb_mod, "_embedder", EMB)
    await _seed(session)

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/v1/knowledge/search", params={"q": "Lightning Strike"})
            assert r.status_code == 422  # game is required by the schema itself
            r = await c.get(
                "/api/v1/knowledge/search",
                params={"game": "poe2", "q": "Lightning Strike", "k": 50},
            )
            assert r.status_code == 200
            games = {h["chunk"]["metadata"]["game"] for h in r.json()}
            assert games == {"poe2"}
            for h in r.json():
                assert h["chunk"]["metadata"]["source_url"].startswith(
                    "https://www.pathofexile.com/"
                )
                assert h["chunk"]["metadata"]["retrieved_at"]
            r = await c.get("/api/v1/knowledge/patches", params={"game": "poe"})
            assert r.json()[0]["patch"] == "3.29"
            r = await c.get("/api/v1/knowledge/stats")
            assert r.json()["chunks"] == len(POE.chunks) + len(POE2.chunks)
    finally:
        app.dependency_overrides.clear()
