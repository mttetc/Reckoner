"""LLM clients behind one small protocol.

- ``AnthropicClient``: Claude via the Anthropic SDK (Messages API with tool use).
- ``ScriptedLLM``: no model at all — a deterministic policy that calls tools and composes a
  templated answer from their results. Used by tests, CI and the offline demo. It is labelled as
  such in every answer (``model = "scripted"``); it never pretends to be a model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import settings


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    raw_content: Any = None  # provider-native assistant content, echoed back on the next turn


class LLMClient(Protocol):
    name: str

    async def complete(
        self, system: str, messages: list[dict], tools: list[dict]
    ) -> LLMResponse: ...


class OpenAICompatClient:
    """Chat Completions with tools — Ollama, Groq, Mistral, OpenRouter, Gemini (OpenAI mode)…"""

    def __init__(self, base_url: str, model: str, api_key: str | None = None) -> None:
        import httpx

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"openai_compat:{model}@{self.base_url}"
        headers = {"Authorization": f"Bearer {api_key or 'none'}"}
        # Local 7B models on a laptop can take minutes on a cold prompt; retry once on timeout.
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=300)

    @staticmethod
    def _to_openai(system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            content = m["content"]
            if m["role"] == "user" and isinstance(content, list):
                for block in content:  # tool results
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block["content"],
                        }
                    )
            elif m["role"] == "assistant" and isinstance(content, list):
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                calls = [
                    {
                        "id": b["id"],
                        "type": "function",
                        "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                    }
                    for b in content
                    if b.get("type") == "tool_use"
                ]
                msg: dict[str, Any] = {"role": "assistant", "content": text or None}
                if calls:
                    msg["tool_calls"] = calls
                out.append(msg)
            else:
                out.append({"role": m["role"], "content": content})
        return out

    async def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body = {
            "model": self.model,
            "messages": self._to_openai(system, messages),
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ],
            "temperature": 0,
            "max_tokens": 900,  # a runaway generation must end; answers are meant to be short
        }
        import httpx

        try:
            r = await self._client.post("/chat/completions", json=body)
        except httpx.ReadTimeout:
            r = await self._client.post("/chat/completions", json=body)
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        msg = choice["message"]
        out = LLMResponse(
            text=msg.get("content") or "", stop_reason=choice.get("finish_reason") or "stop"
        )
        usage = data.get("usage") or {}
        out.input_tokens = int(usage.get("prompt_tokens") or 0)
        out.output_tokens = int(usage.get("completion_tokens") or 0)
        for i, call in enumerate(msg.get("tool_calls") or []):
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            out.tool_calls.append(ToolCall(call.get("id") or f"call_{i}", fn.get("name", ""), args))
        # raw_content stays None: the runner rebuilds a provider-neutral assistant turn.
        return out


class AnthropicClient:
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.name = f"anthropic:{model}"

    async def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=system,
            messages=messages,
            tools=[
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["input_schema"],
                }
                for t in tools
            ],
        )
        out = LLMResponse(
            stop_reason=resp.stop_reason or "end_turn",
            raw_content=[b.model_dump() for b in resp.content],
        )
        out.input_tokens = resp.usage.input_tokens
        out.output_tokens = resp.usage.output_tokens
        for block in resp.content:
            if block.type == "text":
                out.text += block.text
            elif block.type == "tool_use":
                out.tool_calls.append(ToolCall(block.id, block.name, dict(block.input)))
        return out


_CLASSES = ["duelist", "marauder", "ranger", "scion", "shadow", "templar", "witch"]
_SUBCLASSES = [
    "slayer",
    "gladiator",
    "champion",
    "juggernaut",
    "berserker",
    "chieftain",
    "deadeye",
    "raider",
    "warden",
    "pathfinder",
    "ascendant",
    "reliquarian",
    "assassin",
    "saboteur",
    "trickster",
    "inquisitor",
    "hierophant",
    "guardian",
    "necromancer",
    "occultist",
    "elementalist",
]
_KNOWLEDGE_HINT = re.compile(
    r"\b(patch|changed?|changes|nerf|buff|hotfix|notes?|fixed|what happened)\b", re.I
)


class ScriptedLLM:
    """Deterministic policy: one tool round, then a templated answer. Not a model."""

    name = "scripted"

    async def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        user = next(m for m in messages if m["role"] == "user")
        question = (
            user["content"] if isinstance(user["content"], str) else json.dumps(user["content"])
        )
        game = "poe2" if re.search(r"\bpoe ?2\b|path of exile 2", question, re.I) else "poe"
        tool_results = [
            m for m in messages if m["role"] == "user" and isinstance(m["content"], list)
        ]
        if not tool_results:
            return LLMResponse(stop_reason="tool_use", tool_calls=self._plan(question, game))
        return LLMResponse(
            text=self._compose(tool_results[-1]["content"], game), stop_reason="end_turn"
        )

    def _plan(self, question: str, game: str) -> list[ToolCall]:
        q = question.lower()
        if "[build code attached]" in q:
            return [ToolCall("t1", "analyze_build_code", {})]
        if _KNOWLEDGE_HINT.search(q):
            topic = re.sub(
                r"\b(what|which|did|does|has|have|in|the|to|of|a|an|patch|changed?|changes|notes?)\b",
                " ",
                q,
            )
            topic = re.sub(r"\s+", " ", topic).strip() or "changes"
            return [
                ToolCall("t1", "get_patch_changes", {"game": game}),
                ToolCall("t2", "search_knowledge", {"game": game, "query": topic, "k": 5}),
            ]
        args: dict[str, Any] = {"game": game, "limit": 5}
        for c in _CLASSES:
            if c in q:
                args["class_name"] = c
        for s in _SUBCLASSES:
            if s in q:
                args["subclass"] = s
        m = re.search(
            r"(lightning strike|cyclone|discharge|spectral throw|holy sweep|void sphere"
            r"|soulrend|storm brand|rolling magma)",
            q,
        )
        if m:
            args["main_skill"] = m.group(1)
        if "tank" in q:
            args["sort"] = "ehp_total"
        return [ToolCall("t1", "search_builds", args), ToolCall("t2", "corpus_stats", {})]

    @staticmethod
    def _compose(results: list[dict], game: str) -> str:
        by_id = {}
        for block in results:
            try:
                by_id[block["tool_use_id"]] = (
                    json.loads(block["content"])
                    if isinstance(block["content"], str)
                    else block["content"]
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                by_id[block.get("tool_use_id", "?")] = {"error": str(block.get("content"))}
        lines: list[str] = []
        for res in by_id.values():
            if isinstance(res, dict) and res.get("error"):
                lines.append(f"A tool refused: {res['error']}")
                continue
            if isinstance(res, dict) and "items" in res and "total" in res:
                pretty_game = "Path of Exile 2" if game == "poe2" else "Path of Exile"
                lines.append(
                    f"No build matches in {pretty_game}."
                    if res["total"] == 0
                    else f"{res['total']} build{'s' if res['total'] > 1 else ''} match "
                    f"in {pretty_game}."
                )
                for it in res["items"]:
                    dps = it["metrics"].get("dps.total", {})
                    life = it["metrics"].get("life.max", {})
                    dps_s = (
                        f"{dps['value']:,.1f} DPS (calculated by {dps['engine']})"
                        if dps.get("value") is not None
                        else "DPS not in the export"
                    )
                    life_s = (
                        f"{life['value']:,.0f} life"
                        if life.get("value") is not None
                        else "life unknown"
                    )
                    ch = it["character"]
                    src = (
                        f" — source: {it['source']['title']}"
                        if it.get("source") and it["source"].get("title")
                        else ""
                    )
                    who = f"{ch.get('class_name')} {ch.get('subclass') or ''}"
                    lines.append(
                        f"• {who} · {it['main_skill']} · {dps_s} · {life_s}"
                        f" · patch {it['game_version']}{src}"
                    )
            elif isinstance(res, dict) and "snapshots" in res:
                lines.append(f"{res['snapshots']} builds are known in total.")
            elif isinstance(res, dict) and "patches" in res:
                pretty_game = "Path of Exile 2" if game == "poe2" else "Path of Exile"
                lines.append(
                    f"Patch notes known for {pretty_game}: "
                    + ", ".join(p["patch"] for p in res["patches"])
                    + "."
                )
            elif isinstance(res, list) and res and "excerpt" in res[0]:
                pretty_game = "Path of Exile 2" if game == "poe2" else "Path of Exile"
                lines.append(f"From the official {pretty_game} patch notes:")
                for h in res[:3]:
                    lines.append(
                        f"• [{h['game']} {h['patch']} · {h['heading'] or h['title']}] "
                        f"{h['excerpt'][:200]} (source: {h['source_url']})"
                    )
            elif isinstance(res, dict) and "main_skill" in res:
                m = res["metrics"]
                dps = m.get("dps.total", {})
                dps_s = (
                    f"{dps['value']:,.1f} (calculated by {dps['engine']}, "
                    f"patch {dps['game_version']})"
                    if dps.get("value") is not None
                    else "unknown"
                )
                ch = res["character"]
                lines.append(
                    f"Your build: {ch.get('class_name')} {ch.get('subclass') or ''}, "
                    f"{res['main_skill']}, patch {res['game_version']}. DPS {dps_s}."
                )
        return (
            "\n".join(lines)
            or "The tools returned nothing usable; I cannot answer without inventing."
        )


def get_llm() -> LLMClient:
    """Configured provider, or the scripted policy when the provider cannot work at all."""
    if settings.llm == "anthropic":
        if settings.anthropic_api_key:
            return AnthropicClient(settings.anthropic_api_key, settings.llm_model)
        return ScriptedLLM()
    if settings.llm == "openai_compat":
        return OpenAICompatClient(settings.llm_base_url, settings.llm_model, settings.llm_api_key)
    return ScriptedLLM()
