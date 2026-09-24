"""LangGraph spike: the audit node sends unverified numbers back to the model once."""

import pytest

from app.agent.graph import ask
from app.agent.llm import LLMResponse, ScriptedLLM, ToolCall

pytestmark = pytest.mark.asyncio


class Inventive(ScriptedLLM):
    """Calls a tool, then invents a number, then corrects itself when told."""

    def __init__(self):
        self.prompts: list[str] = []

    async def complete(self, system, messages, tools):
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], str) and len(messages) == 1:
            calls = [ToolCall("t1", "list_games", {})]
            return LLMResponse(stop_reason="tool_use", tool_calls=calls)
        if isinstance(last["content"], str):  # the audit's correction request
            self.prompts.append(last["content"])
            return LLMResponse(text="There are games available; I do not have a DPS figure.")
        return LLMResponse(text="The build deals 123456 DPS.")


async def test_unverified_number_triggers_one_correction(session):
    from app.db.repository import CorpusRepository
    from app.knowledge.embedder import HashEmbedder
    from app.knowledge.repository import KnowledgeRepository

    llm = Inventive()
    a = await ask(
        CorpusRepository(session), KnowledgeRepository(session, HashEmbedder()), "DPS?", llm=llm
    )
    assert [s.tool for s in a.steps] == ["list_games"]
    assert len(llm.prompts) == 1 and "123456" in llm.prompts[0]
    assert "123456" not in a.text and a.audit.clean
