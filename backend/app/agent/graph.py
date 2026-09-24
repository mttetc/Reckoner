"""The agent as a LangGraph state machine (ADR-013, default engine).

Same signature and ``AgentAnswer`` as the hand-written loop in ``runner.py`` (kept behind
``agent_engine=loop``); same tools, same LLM clients (the provider protocol and the scripted
policy are reused as-is, no LangChain chat model). What the graph adds over the loop:

- an explicit ``audit`` node with a correction edge: when the number audit flags unverified
  values, the model gets one chance to rewrite the answer using only tool values;
- optional checkpointing (``thread_id``) so a conversation can be resumed across calls.
"""

from __future__ import annotations

import inspect
import json
import time
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.audit import audit_answer
from app.agent.llm import LLMClient, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, ToolCallRecord, ToolContext, run_tool
from app.config import settings
from app.domain.evidence import Evidence
from app.domain.ports import BuildStore, KnowledgeStore


def _extend(a: list, b: list) -> list:
    return a + b


def _add(a: int, b: int) -> int:
    return a + b


class AgentState(TypedDict, total=False):
    messages: Annotated[list[dict], _extend]
    steps: Annotated[list[ToolCallRecord], _extend]
    evidence: Annotated[list[Evidence], _extend]
    degraded: Annotated[list[str], _extend]
    results_for_audit: Annotated[list[Any], _extend]
    input_tokens: Annotated[int, _add]
    output_tokens: Annotated[int, _add]
    model_calls: Annotated[int, _add]
    corrections: Annotated[int, _add]
    pending: list[dict]  # tool calls awaiting execution (overwritten each model turn)
    text: str
    question: str
    retry: bool


def _tool_schemas() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema()}
        for t in TOOLS.values()
    ]


def _dump(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def build_graph(
    llm: LLMClient,
    ctx: ToolContext,
    *,
    max_steps: int,
    max_corrections: int = 1,
    on_event=None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    async def emit(event: dict[str, Any]) -> None:
        if on_event is None:
            return
        out = on_event(event)
        if inspect.isawaitable(out):
            await out

    async def model(state: AgentState) -> dict:
        resp = await llm.complete(SYSTEM_PROMPT, state["messages"], _tool_schemas())
        out: dict = {
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "model_calls": 1,
        }
        if not resp.tool_calls:
            out["text"] = resp.text.strip()
            out["pending"] = []
            return out
        assistant_content = resp.raw_content or (
            ([{"type": "text", "text": resp.text}] if resp.text else [])
            + [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.args}
                for c in resp.tool_calls
            ]
        )
        out["messages"] = [{"role": "assistant", "content": assistant_content}]
        out["pending"] = [{"id": c.id, "name": c.name, "args": c.args} for c in resp.tool_calls]
        return out

    async def tools(state: AgentState) -> dict:
        steps, evidence, degraded, results, blocks = [], [], [], [], []
        seen = {e.statement + "|" + (e.source_url or "") for e in state.get("evidence", [])}
        for call in state["pending"]:
            await emit(
                {"type": "step_start", "id": call["id"], "tool": call["name"], "args": call["args"]}
            )
            result, record = await run_tool(ctx, call["name"], call["args"])
            steps.append(record)
            await emit(
                {
                    "type": "step_end",
                    "id": call["id"],
                    "tool": call["name"],
                    "ok": record.ok,
                    "summary": record.summary,
                    "error": record.error,
                }
            )
            if result is None:
                degraded.append(f"{call['name']}: {record.error}")
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": _dump({"error": record.error}),
                        "is_error": True,
                    }
                )
                continue
            results.append(result.data)
            for ev in result.evidence:
                key = ev.statement + "|" + (ev.source_url or "")
                if key not in seen:
                    seen.add(key)
                    evidence.append(ev)
            blocks.append(
                {"type": "tool_result", "tool_use_id": call["id"], "content": _dump(result.data)}
            )
        return {
            "messages": [{"role": "user", "content": blocks}],
            "steps": steps,
            "evidence": evidence,
            "degraded": degraded,
            "results_for_audit": results,
            "pending": [],
        }

    async def audit(state: AgentState) -> dict:
        a = audit_answer(
            state.get("text", ""), state.get("results_for_audit", []), question=state["question"]
        )
        out: dict = {"retry": False}
        if a.unverified and state.get("corrections", 0) < max_corrections:
            out["corrections"] = 1
            out["retry"] = True
            out["messages"] = [
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": state["text"]}],
                },
                {
                    "role": "user",
                    "content": (
                        "Audit: these numbers do not appear in any tool result: "
                        + ", ".join(a.unverified)
                        + ". Rewrite your answer using only values returned by the tools; "
                        "if a value is unknown, say so."
                    ),
                },
            ]
        return out

    def after_model(state: AgentState) -> str:
        if state.get("pending"):
            return "tools"
        return "audit"

    def after_tools(state: AgentState) -> str:
        if state.get("model_calls", 0) >= max_steps:
            return "limit"
        return "model"

    def after_audit(state: AgentState) -> str:
        return "model" if state.get("retry") else END

    async def limit(state: AgentState) -> dict:
        return {
            "degraded": ["step limit reached before a final answer"],
            "text": "Step limit reached before a final answer; the tool results are all I have.",
        }

    g = StateGraph(AgentState)
    g.add_node("model", model)
    g.add_node("tools", tools)
    g.add_node("audit", audit)
    g.add_node("limit", limit)
    g.add_edge(START, "model")
    g.add_conditional_edges("model", after_model, {"tools": "tools", "audit": "audit"})
    g.add_conditional_edges("tools", after_tools, {"model": "model", "limit": "limit"})
    g.add_conditional_edges("audit", after_audit, {"model": "model", END: END})
    g.add_edge("limit", END)
    return g.compile(checkpointer=checkpointer)


async def ask(
    builds: BuildStore,
    knowledge: KnowledgeStore,
    question: str,
    *,
    game: str | None = None,
    code: str | None = None,
    llm: LLMClient | None = None,
    max_steps: int | None = None,
    on_event=None,
    checkpointer: BaseCheckpointSaver | None = None,
    thread_id: str | None = None,
):
    from app.agent.runner import AgentAnswer, follow_ups

    t0 = time.monotonic()
    llm = llm or get_llm()
    ctx = ToolContext(builds=builds, knowledge=knowledge, game=game, code=code)
    content = question
    if game:
        content += f"\n\n[game: {game}]"
    if code:
        content += "\n\n[build code attached]"
    graph = build_graph(
        llm,
        ctx,
        max_steps=max_steps or settings.agent_max_steps,
        on_event=on_event,
        checkpointer=checkpointer,
    )
    config: dict = {"recursion_limit": 4 * (max_steps or settings.agent_max_steps) + 8}
    if checkpointer is not None:
        config["configurable"] = {"thread_id": thread_id or "default"}
    final = await graph.ainvoke(
        {"messages": [{"role": "user", "content": content}], "pending": [], "question": question},
        config=config,
    )
    answer = AgentAnswer(text=final.get("text", ""), model=llm.name)
    answer.steps = list(final.get("steps", []))
    answer.evidence = list(final.get("evidence", []))
    answer.degraded = list(final.get("degraded", []))
    answer.input_tokens = final.get("input_tokens", 0)
    answer.output_tokens = final.get("output_tokens", 0)
    answer.audit = audit_answer(answer.text, final.get("results_for_audit", []), question=question)
    answer.suggestions = follow_ups(answer, code is not None)
    if not answer.steps:
        answer.degraded.append("no tool was used: the answer contains nothing verifiable")
    answer.duration_ms = int((time.monotonic() - t0) * 1000)
    return answer
