"""The tool-calling loop, its trace, its evidence and its number audit."""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.audit import Audit, audit_answer
from app.agent.llm import LLMClient, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, ToolCallRecord, ToolContext, run_tool
from app.config import settings
from app.domain.evidence import Evidence

EventHook = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass
class AgentAnswer:
    text: str
    model: str
    steps: list[ToolCallRecord] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    audit: Audit = field(default_factory=Audit)
    degraded: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
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
    on_event: EventHook | None = None,
) -> AgentAnswer:
    """``on_event`` receives step_start / step_end dicts as tools run — for live UIs."""
    t0 = time.monotonic()

    async def emit(event: dict[str, Any]) -> None:
        if on_event is None:
            return
        out = on_event(event)
        if inspect.isawaitable(out):
            await out

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
            await emit({"type": "step_start", "id": call.id, "tool": call.name, "args": call.args})
            result, record = await run_tool(ctx, call.name, call.args)
            answer.steps.append(record)
            await emit(
                {
                    "type": "step_end",
                    "id": call.id,
                    "tool": call.name,
                    "ok": record.ok,
                    "summary": record.summary,
                    "error": record.error,
                }
            )
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

    answer.audit = audit_answer(answer.text, results_for_audit, question=question)
    answer.suggestions = follow_ups(answer, code is not None)
    if not answer.steps:
        answer.degraded.append("no tool was used: the answer contains nothing verifiable")
    answer.duration_ms = int((time.monotonic() - t0) * 1000)
    return answer


def follow_ups(answer: AgentAnswer, has_code: bool) -> list[str]:
    """Deterministic next questions, derived from what the tools actually returned."""
    tools = [s.tool for s in answer.steps if s.ok]
    out: list[str] = []
    if "analyze_build_code" in tools or has_code:
        out += [
            "What would change if I fought an Uber boss?",
            "Which passives matter most for this build's damage?",
            "What changed for this build's main skill in the latest patch?",
        ]
    elif "search_builds" in tools:
        out += [
            "Which of these is the tankiest?",
            "Tell me more about the first one",
            "Show me the same for another class",
        ]
    elif "get_patch_changes" in tools or "search_knowledge" in tools:
        out += [
            "What about the other game?",
            "Find me a build using that skill",
            "What else changed in that patch?",
        ]
    if not out:
        out = ["Find me a tanky build", "What changed in the latest patch?"]
    return out[:3]
