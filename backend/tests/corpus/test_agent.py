"""Agent loop with the scripted policy (no model): tools, trace, evidence, audit, degraded."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.llm import ScriptedLLM
from app.agent.runner import ask
from app.corpus.pipeline import FetchedCode, ingest_many
from app.db.engine import get_session
from app.db.repository import SourceRef
from app.domain.build import GameId
from app.games import _ADAPTERS
from app.games.poe.engine import PobHeadless
from app.knowledge.embedder import HashEmbedder
from app.knowledge.ingest import ingest_documents
from app.main import app
from tests.corpus.test_knowledge_isolation import POE, POE2  # noqa: E402

pytestmark = pytest.mark.asyncio
LLM = ScriptedLLM()


async def _seed(session, all_codes):
    await ingest_many(
        session,
        [
            FetchedCode(
                c,
                SourceRef(kind="paste", url=f"https://pobb.in/{n}", game="poe", title=n, terms="t"),
            )
            for n, c in all_codes
        ],
    )
    await ingest_documents(session, [POE, POE2], embedder=HashEmbedder())


async def test_build_question_uses_tools_and_every_number_is_traceable(session, all_codes):
    await _seed(session, all_codes)
    a = await ask(session, "Find me a Duelist Lightning Strike build", llm=LLM)
    assert [s.tool for s in a.steps] == ["search_builds", "corpus_stats"]
    assert all(s.ok for s in a.steps)
    assert "Slayer" in a.text and "Vaal Lightning Strike" in a.text
    assert a.audit.checked > 0 and a.audit.clean, a.audit.unverified
    assert any(
        e.statement.startswith("Duelist Slayer") and "dps.total" in e.statement for e in a.evidence
    )
    assert all(e.provenance.status == "calculated" for e in a.evidence)
    assert a.model == "scripted" and a.degraded == []


async def test_knowledge_question_is_game_isolated(session, all_codes, monkeypatch):
    from app.knowledge import embedder as emb_mod

    monkeypatch.setattr(emb_mod, "_embedder", HashEmbedder())
    await _seed(session, all_codes)
    a = await ask(session, "What changed for Lightning Strike in the latest PoE 2 patch?", llm=LLM)
    assert [s.tool for s in a.steps] == ["get_patch_changes", "search_knowledge"]
    assert "0.5" in a.text and "3.29" not in a.text
    assert a.evidence and all(e.provenance.game == "poe2" for e in a.evidence)
    assert all(e.provenance.status == "claimed" and e.source_url for e in a.evidence)


async def test_pasted_code_is_analysed(session, code_modern):
    a = await ask(session, "How strong is my build?", code=code_modern, llm=LLM)
    assert [s.tool for s in a.steps] == ["analyze_build_code"]
    assert "Duelist Slayer" in a.text and "Path of Building" in a.text
    assert a.audit.clean, a.audit.unverified


async def test_empty_corpus_is_stated_not_padded(session):
    a = await ask(session, "Find me a Witch build", llm=LLM)
    assert "0 build(s)" in a.text
    assert a.audit.clean


async def test_refused_tool_is_a_degraded_state_not_a_guess(session, code_modern, monkeypatch):
    from app.agent.llm import LLMResponse, ToolCall

    class OneShot(ScriptedLLM):
        async def complete(self, system, messages, tools):
            if not any(isinstance(m["content"], list) for m in messages if m["role"] == "user"):
                return LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        ToolCall(
                            "t1",
                            "calculate_build",
                            {
                                "modifications": [
                                    {"kind": "tree.deallocate", "payload": {"node_id": 41119}}
                                ]
                            },
                        )
                    ],
                )
            return LLMResponse(text="The engine was unavailable, so no recalculated figure.")

    monkeypatch.setattr(_ADAPTERS[GameId.POE], "_engine", PobHeadless(pob_src=None))
    a = await ask(session, "What if I drop Lethality?", code=code_modern, llm=OneShot())
    assert a.steps[0].tool == "calculate_build" and a.steps[0].ok is False
    assert "engine_unavailable" in a.steps[0].error
    assert a.degraded and "calculate_build" in a.degraded[0]
    assert a.audit.clean


async def test_api_contract(session, all_codes):
    await _seed(session, all_codes)

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post(
                "/api/v1/ask", json={"question": "Find me a Templar build", "game": "poe"}
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["model"] == "scripted"
            assert body["steps"][0]["tool"] == "search_builds"
            assert body["audit"]["clean"] is True
            assert body["evidence"] and body["evidence"][0]["provenance"]["status"] == "calculated"
            r = await c.post("/api/v1/ask", json={"question": "hi"})
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_patch_changes_with_topic_defaults_to_latest_patch(session, all_codes):
    from app.agent.tools import PatchChangesArgs, ToolContext, run_tool

    await _seed(session, all_codes)
    ctx = ToolContext(session=session)
    result, rec = await run_tool(
        ctx, "get_patch_changes", {"game": "poe2", "topic": "Lightning Strike"}
    )
    assert rec.ok, rec.error
    assert result.data["patch"] == "0.5" and result.data["passages"]
    assert all(e.provenance.game == "poe2" for e in result.evidence)
    listing, rec = await run_tool(ctx, "get_patch_changes", {"game": "poe2"})
    assert rec.ok and [p["patch"] for p in listing.data["patches"]] == ["0.5"]
    assert PatchChangesArgs(game="poe2").patch is None
