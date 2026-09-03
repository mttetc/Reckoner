"""The tool-calling loop, its trace, its evidence and its number audit."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.audit import Audit, audit_answer
from app.agent.llm import LLMClient, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, ToolCallRecord, ToolContext, run_tool
from app.config import settings
from app.domain.evidence import Evidence


@dataclass
class AgentAnswer:
    text: str
    model: str
    steps: list[ToolCallRecord] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    audit: Audit = field(default_factory=Audit)
    degraded: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


def _tool_schemas() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema()}
        for t in TOOLS.values()
    ]


def _dump(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


async def ask(
    session: AsyncSession,
    question: str,
    *,
    game: str | None = None,
    code: str | None = None,
    llm: LLMClient | None = None,
    max_steps: int | None = None,
) -> AgentAnswer:
    t0 = time.monotonic()
    llm = llm or get_llm()
    ctx = ToolContext(session=session, game=game, code=code)
    content = question
    if game:
        content += f"\n\n[game: {game}]"
    if code:
        content += "\n\n[build code attached]"
    messages: list[dict] = [{"role": "user", "content": content}]
    answer = AgentAnswer(text="", model=llm.name)
    results_for_audit: list = []
    seen_evidence: set[str] = set()

    for _ in range(max_steps or settings.agent_max_steps):
        resp = await llm.complete(SYSTEM_PROMPT, messages, _tool_schemas())
        answer.input_tokens += resp.input_tokens
        answer.output_tokens += resp.output_tokens
        if not resp.tool_calls:
            answer.text = resp.text.strip()
            break
        # Echo the assistant turn (provider-native when available), then run the tools.
        assistant_content = resp.raw_content or (
            ([{"type": "text", "text": resp.text}] if resp.text else [])
            + [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.args}
                for c in resp.tool_calls
            ]
        )
        messages.append({"role": "assistant", "content": assistant_content})
        tool_blocks = []
        for call in resp.tool_calls:
            result, record = await run_tool(ctx, call.name, call.args)
            answer.steps.append(record)
            if result is None:
                answer.degraded.append(f"{call.name}: {record.error}")
                tool_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": _dump({"error": record.error}),
                        "is_error": True,
                    }
                )
                continue
            results_for_audit.append(result.data)
            for ev in result.evidence:
                key = ev.statement + "|" + (ev.source_url or "")
                if key not in seen_evidence:
                    seen_evidence.add(key)
                    answer.evidence.append(ev)
            tool_blocks.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": _dump(result.data)}
            )
        messages.append({"role": "user", "content": tool_blocks})
    else:
        answer.degraded.append("step limit reached before a final answer")
        answer.text = (
            answer.text
            or "Step limit reached before a final answer; the tool results are all I have."
        )

    answer.audit = audit_answer(answer.text, results_for_audit)
    if not answer.steps:
        answer.degraded.append("no tool was used: the answer contains nothing verifiable")
    answer.duration_ms = int((time.monotonic() - t0) * 1000)
    return answer
