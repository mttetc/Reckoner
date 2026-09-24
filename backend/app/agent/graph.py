"""The agent as a LangGraph state machine (ADR-013, default engine).

Same signature and ``AgentAnswer`` as the hand-written loop in ``runner.py`` (kept behind
``agent_engine=loop``); same tools, same LLM clients (the provider protocol and the scripted
policy are reused as-is, no LangChain chat model). What the graph adds over the loop:

- an explicit ``audit`` node with a correction edge: when the number audit flags unverified
  values, the model gets one chance to rewrite the answer using only tool values;
- conversation memory: with a checkpointer and a ``thread_id`` the conversation resumes across
  calls. The model sees the last ``agent_memory_turns`` turns; a build code attached earlier in
  the conversation stays available to the tools; numbers returned by tools in earlier turns stay
  verifiable by the audit.

State is split in two: conversation-level fields accumulate (``messages``, ``turns``,
``results_for_audit``, ``code``, ``game``); per-turn fields are reset by ``begin`` and reported in
the answer (``steps``, ``evidence``, ``degraded``, tokens).
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


class AgentState(TypedDict, total=False):
    # conversation-level
    messages: Annotated[list[dict], _extend]
    turns: Annotated[list[int], _extend]  # index in ``messages`` where each turn starts
    results_for_audit: Annotated[list[Any], _extend]
    code: str | None
    game: str | None
    # per-turn (reset by ``begin``)
    question: str
    steps: list[ToolCallRecord]
    evidence: list[Evidence]
    degraded: list[str]
    input_tokens: int
    output_tokens: int
    model_calls: int
    corrections: int
    pending: list[dict]  # tool calls awaiting execution
    text: str
    retry: bool


def _tool_schemas() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema()}
        for t in TOOLS.values()
    ]


def _dump(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def window(messages: list[dict], turns: list[int], keep: int) -> list[dict]:
    """The last ``keep`` turns, cut on turn boundaries so tool_use/tool_result pairs stay whole."""
    if keep <= 0 or len(turns) <= keep:
        return messages
    return messages[turns[-keep] :]


def build_graph(
    llm: LLMClient,
    ctx: ToolContext,
    *,
    max_steps: int,
    max_corrections: int = 1,
    memory_turns: int | None = None,
    on_event=None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    keep = settings.agent_memory_turns if memory_turns is None else memory_turns

    async def emit(event: dict[str, Any]) -> None:
        if on_event is None:
            return
        out = on_event(event)
        if inspect.isawaitable(out):
            await out

    async def begin(state: AgentState) -> dict:
        content = state["question"]
        if ctx.game:
            content += f"\n\n[game: {ctx.game}]"
        if ctx.code:
            content += "\n\n[build code attached]"
        return {
            "messages": [{"role": "user", "content": content}],
            "turns": [len(state.get("messages", []))],
            "code": ctx.code,
            "game": ctx.game,
            "steps": [],
            "evidence": [],
            "degraded": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "model_calls": 0,
            "corrections": 0,
            "pending": [],
            "text": "",
            "retry": False,
        }

    async def model(state: AgentState) -> dict:
        visible = window(state["messages"], state["turns"], keep)
        resp = await llm.complete(SYSTEM_PROMPT, visible, _tool_schemas())
        out: dict = {
            "input_tokens": state["input_tokens"] + resp.input_tokens,
            "output_tokens": state["output_tokens"] + resp.output_tokens,
            "model_calls": state["model_calls"] + 1,
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
        seen = {e.statement + "|" + (e.source_url or "") for e in state["evidence"]}
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
            "steps": state["steps"] + steps,
            "evidence": state["evidence"] + evidence,
            "degraded": state["degraded"] + degraded,
            "results_for_audit": results,
            "pending": [],
        }

    async def audit(state: AgentState) -> dict:
        text = state["text"]
        a = audit_answer(text, state.get("results_for_audit", []), question=state["question"])
        if a.unverified and state["corrections"] < max_corrections:
            return {
                "corrections": state["corrections"] + 1,
                "retry": True,
                "messages": [
                    {"role": "assistant", "content": [{"type": "text", "text": text}]},
                    {
                        "role": "user",
                        "content": (
                            "Audit: these numbers do not appear in any tool result: "
                            + ", ".join(a.unverified)
                            + ". Rewrite your answer using only values returned by the tools; "
                            "if a value is unknown, say so."
                        ),
                    },
                ],
            }
        out: dict = {"retry": False}
        if text:  # the final answer joins the conversation for the next turn
            out["messages"] = [{"role": "assistant", "content": [{"type": "text", "text": text}]}]
        return out

    async def limit(state: AgentState) -> dict:
        text = "Step limit reached before a final answer; the tool results are all I have."
        return {
            "degraded": state["degraded"] + ["step limit reached before a final answer"],
            "text": text,
            "messages": [{"role": "assistant", "content": [{"type": "text", "text": text}]}],
        }

    def after_model(state: AgentState) -> str:
        return "tools" if state["pending"] else "audit"

    def after_tools(state: AgentState) -> str:
        return "limit" if state["model_calls"] >= max_steps else "model"

    def after_audit(state: AgentState) -> str:
        return "model" if state["retry"] else END

    g = StateGraph(AgentState)
    g.add_node("begin", begin)
    g.add_node("model", model)
    g.add_node("tools", tools)
    g.add_node("audit", audit)
    g.add_node("limit", limit)
    g.add_edge(START, "begin")
    g.add_edge("begin", "model")
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
    thread_id: str | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """``thread_id`` resumes a conversation. The checkpointer defaults to the configured one;
    when it cannot be reached the turn still runs, without memory, and says so in ``degraded``."""
    from app.agent.memory import get_checkpointer
    from app.agent.runner import AgentAnswer, follow_ups

    t0 = time.monotonic()
    llm = llm or get_llm()
    steps = max_steps or settings.agent_max_steps
    degraded: list[str] = []

    if thread_id and checkpointer is None:
        try:
            checkpointer = await get_checkpointer()
        except Exception as exc:  # the store is a degraded state, not a reason to fail the turn
            degraded.append(f"conversation memory unavailable: {type(exc).__name__}: {exc}"[:300])
    if checkpointer is None:
        thread_id = None
    config: dict = {"recursion_limit": 4 * steps + 8}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    # A build code or a game hint from an earlier turn stays in force until replaced.
    if thread_id and (code is None or game is None):
        probe = build_graph(
            llm,
            ToolContext(builds=builds, knowledge=knowledge),
            max_steps=steps,
            checkpointer=checkpointer,
        )
        prior = (await probe.aget_state(config)).values or {}
        code = code if code is not None else prior.get("code")
        game = game if game is not None else prior.get("game")

    ctx = ToolContext(builds=builds, knowledge=knowledge, game=game, code=code)
    graph = build_graph(llm, ctx, max_steps=steps, on_event=on_event, checkpointer=checkpointer)
    final = await graph.ainvoke({"question": question}, config=config)

    answer = AgentAnswer(text=final.get("text", ""), model=llm.name, thread_id=thread_id)
    answer.steps = list(final.get("steps", []))
    answer.evidence = list(final.get("evidence", []))
    answer.degraded = degraded + list(final.get("degraded", []))
    answer.input_tokens = final.get("input_tokens", 0)
    answer.output_tokens = final.get("output_tokens", 0)
    answer.audit = audit_answer(answer.text, final.get("results_for_audit", []), question=question)
    answer.suggestions = follow_ups(answer, code is not None)
    if not answer.steps:
        answer.degraded.append("no tool was used: the answer contains nothing verifiable")
    answer.duration_ms = int((time.monotonic() - t0) * 1000)
    return answer
