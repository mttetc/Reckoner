"""Conversation memory (graph engine + checkpointer): a thread resumes across calls."""

import uuid

import pytest

from app.agent.graph import ask
from app.agent.llm import ScriptedLLM
from app.db.repository import CorpusRepository
from app.knowledge.embedder import HashEmbedder
from app.knowledge.repository import KnowledgeRepository

pytestmark = pytest.mark.asyncio
LLM = ScriptedLLM()


def _stores(session):
    return CorpusRepository(session), KnowledgeRepository(session, HashEmbedder())


async def test_code_attached_earlier_stays_available_to_the_tools(session, code_modern):
    builds, knowledge = _stores(session)
    thread = str(uuid.uuid4())
    first = await ask(
        builds, knowledge, "How strong is my build?", code=code_modern, llm=LLM, thread_id=thread
    )
    assert [s.tool for s in first.steps] == ["analyze_build_code"] and first.audit.clean
    assert first.thread_id == thread

    # Same thread, no code sent: the conversation remembers it.
    second = await ask(builds, knowledge, "How strong is my build?", llm=LLM, thread_id=thread)
    assert [s.tool for s in second.steps] == ["analyze_build_code"]
    assert second.steps[0].ok, second.steps[0].error
    assert "Duelist Slayer" in second.text and second.audit.clean
    # Per-turn fields are per turn: one step, not two.
    assert len(second.steps) == 1

    # A fresh thread has no such memory: no code reaches the tools, nothing is guessed.
    third = await ask(
        builds, knowledge, "How strong is my build?", llm=LLM, thread_id=str(uuid.uuid4())
    )
    assert "analyze_build_code" not in [s.tool for s in third.steps]
    assert "Duelist Slayer" not in third.text


async def test_history_is_stored_and_windowed(session, code_modern):
    from app.agent.memory import get_checkpointer

    builds, knowledge = _stores(session)
    thread = str(uuid.uuid4())
    for _ in range(3):
        await ask(
            builds,
            knowledge,
            "How strong is my build?",
            code=code_modern,
            llm=LLM,
            thread_id=thread,
        )
    saver = await get_checkpointer()
    tup = await saver.aget_tuple({"configurable": {"thread_id": thread}})
    values = tup.checkpoint["channel_values"]
    assert len(values["turns"]) == 3
    # Each turn: question, assistant tool_use, tool_result, assistant answer.
    assert len(values["messages"]) == 12
    assert values["messages"][-1]["role"] == "assistant"
    assert values["code"] == code_modern
    # Numbers from earlier turns stay verifiable.
    assert len(values["results_for_audit"]) == 3


async def test_without_thread_there_is_no_memory(session, code_modern):
    builds, knowledge = _stores(session)
    a = await ask(builds, knowledge, "How strong is my build?", code=code_modern, llm=LLM)
    assert a.thread_id is None and a.audit.clean
