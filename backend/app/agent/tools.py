"""Deterministic tools exposed to the model. Each returns JSON-able data plus Evidence."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.domain.build import BuildSnapshot, BuildVariant, GameId, Modification
from app.domain.errors import DomainError
from app.domain.evidence import Evidence
from app.domain.ports import BuildQuery, BuildStore, Hit, KnowledgeStore
from app.domain.provenance import Metric, MetricKey, Provenance, ProvenanceStatus
from app.games import list_adapters
from app.services.analyze import analyze_code
from app.services.corpus import corpus_stats, get_build, search_builds
from app.services.recalculate import recalculate_code

HEADLINE = (
    MetricKey.DPS_TOTAL,
    MetricKey.DPS_FULL,
    MetricKey.MINION_DPS_TOTAL,
    MetricKey.LIFE_MAX,
    MetricKey.ENERGY_SHIELD_MAX,
    MetricKey.EHP_TOTAL,
    MetricKey.RES_FIRE,
    MetricKey.RES_COLD,
    MetricKey.RES_LIGHTNING,
    MetricKey.RES_CHAOS,
)


@dataclass
class ToolContext:
    builds: BuildStore
    knowledge: KnowledgeStore
    game: str | None = None
    code: str | None = None  # a build code pasted with the question, if any


@dataclass
class ToolResult:
    data: Any
    evidence: list[Evidence] = field(default_factory=list)
    summary: str = ""


class ToolError(Exception):
    """Returned to the model as an error result; never raised through to the user."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[ToolContext, BaseModel], Awaitable[ToolResult]]

    def schema(self) -> dict:
        schema = self.args.model_json_schema()
        schema.pop("title", None)
        return schema


# ------------------------------------------------------------------ helpers


def _metric_view(m: Metric) -> dict:
    if m.value is None:
        return {"value": None, "unit": m.unit, "unknown_reason": m.unknown_reason}
    p = m.provenance
    assert p is not None
    return {
        "value": m.value,
        "unit": m.unit,
        "status": p.status.value,
        "source": p.source,
        "engine": p.engine,
        "engine_version": p.engine_version,
        "game_version": p.game_version,
    }


def compact_snapshot(s: BuildSnapshot) -> dict:
    main_group = next(
        (g for g in s.skills if any(gem.name == s.main_skill for gem in g.gems)), None
    )
    dps_total = s.metric(MetricKey.DPS_TOTAL.value)
    dps_full = s.metric(MetricKey.DPS_FULL.value)
    ctx_total = dps_total.provenance.context if dps_total and dps_total.provenance else {}
    ctx_full = dps_full.provenance.context if dps_full and dps_full.provenance else {}
    return {
        "snapshot_id": str(s.id),
        "game": s.game.value,
        "game_version": s.game_version,
        "character": s.character.model_dump(),
        "main_skill": s.main_skill,
        "main_skill_note": (
            f"dps.total is the engine's figure for the skill selected in the export "
            f"({s.main_skill}); source: {ctx_total.get('main_skill_source', 'unknown')}. "
            "A utility or movement skill left selected gives dps.total 0 while dps.full "
            "sums the skills the author flagged."
        ),
        "dps_full_sums": ctx_full.get("aggregates"),
        "main_skill_links": [g.name for g in main_group.gems] if main_group else [],
        "metrics": {
            k.value: _metric_view(m) for k in HEADLINE if (m := s.metric(k.value)) is not None
        },
        "tree_nodes": len(s.tree.node_ids) if s.tree.node_ids else None,
        "items": [it.name or it.base_type for it in s.items if it.name or it.base_type],
    }


GAME_NAMES: dict[str, str] = {
    "poe": "Path of Exile",
    "poe2": "Path of Exile 2",
    "diablo3": "Diablo III",
    "wow": "World of Warcraft",
    "wow_classic": "World of Warcraft Classic",
}


def game_name(game: str) -> str:
    return GAME_NAMES.get(game, game)


def _n(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word if count == 1 else (plural or word + 's')}"


METRIC_LABELS: dict[str, str] = {
    "dps.total": "DPS",
    "dps.full": "Full DPS",
    "minion.dps.total": "Minion DPS",
    "life.max": "Life",
    "energy_shield.max": "Energy shield",
    "ehp.total": "Effective HP",
    "resist.fire": "Fire resistance",
    "resist.cold": "Cold resistance",
    "resist.lightning": "Lightning resistance",
    "resist.chaos": "Chaos resistance",
}


def human_number(value: float, unit: str | None) -> str:
    if unit == "%":
        return f"{value:g}%"
    if unit == "x":
        return f"×{value:g}"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:g}"


def metric_evidence(s: BuildSnapshot, label: str) -> list[Evidence]:
    """One readable sentence per headline number: for players, not for logs."""
    out: list[Evidence] = []
    for k in HEADLINE:
        m = s.metric(k.value)
        if m is None or m.value is None or m.provenance is None:
            continue
        name = METRIC_LABELS.get(k.value, k.value)
        out.append(
            Evidence(
                statement=f"{label} — {name} {human_number(m.value, m.unit)}",
                provenance=m.provenance,
            )
        )
    return out


def _fmt(m: Metric | None) -> str:
    if m is None or m.value is None:
        return "unknown"
    return f"{m.value:,.0f}" if abs(m.value) >= 1000 else f"{m.value:g}"


def _one_line(s: BuildSnapshot, title: str | None, url: str | None) -> str:
    """One self-contained line per build, for the model to copy verbatim (no cross-wiring)."""
    parts = [
        _label(s),
        f"patch {s.game_version or 'unknown'}",
        f"DPS {_fmt(s.metric(MetricKey.DPS_TOTAL.value))}",
        f"life {_fmt(s.metric(MetricKey.LIFE_MAX.value))}",
        f"EHP {_fmt(s.metric(MetricKey.EHP_TOTAL.value))}",
    ]
    if title:
        parts.append(f"source: {title}")
    if url:
        parts.append(url)
    return " · ".join(parts)


def _label(s: BuildSnapshot) -> str:
    c = s.character
    return f"{c.class_name or '?'}{' ' + c.subclass if c.subclass else ''} · {s.main_skill or '?'}"


def knowledge_evidence(h: Hit) -> Evidence:
    md = h.chunk.metadata
    return Evidence(
        statement=(
            f"{game_name(md.game)} patch {md.patch or '?'} — {h.heading or h.title or md.source}"
        ),
        provenance=Provenance(
            status=ProvenanceStatus.CLAIMED,
            source=md.source,
            game=md.game,
            game_version=md.patch,
            recorded_at=md.retrieved_at,
            context={"title": h.title, "heading": h.heading, "similarity": round(h.score, 3)},
        ),
        source_url=md.source_url,
        excerpt=h.chunk.text[:400],
        published_at=md.published_at,
        retrieved_at=md.retrieved_at,
    )


# ------------------------------------------------------------------ tools


class NoArgs(BaseModel):
    pass


async def _list_games(ctx: ToolContext, _: NoArgs) -> ToolResult:
    data = [
        {
            "id": a.game.value,
            "display_name": a.display_name,
            "capabilities": a.capabilities().model_dump(),
        }
        for a in list_adapters()
    ]
    return ToolResult(data=data, summary=f"{len(data)} supported game(s)")


class SearchBuildsArgs(BaseModel):
    game: GameId = Field(description="Game the builds belong to. Never mix games.")
    class_name: str | None = Field(
        default=None,
        description=(
            "Base class. Path of Exile: Duelist, Marauder, Ranger, Scion, Shadow, Templar, Witch."
        ),
    )
    subclass: str | None = Field(
        default=None,
        description=(
            "Specialisation (ascendancy), e.g. Slayer, Juggernaut, Deadeye, Assassin, "
            "Inquisitor, Necromancer. Not a base class."
        ),
    )
    main_skill: str | None = Field(default=None, description="Substring of the main skill name.")
    game_version: str | None = Field(default=None, description="Patch, e.g. 3.29.")
    min_dps: float | None = Field(
        default=None, description="Only when the user gave a number. Never invent a threshold."
    )
    min_life: float | None = Field(default=None, description="Only when the user gave a number.")
    min_ehp: float | None = Field(
        default=None,
        description="Only when the user gave a number. For 'tanky', use sort=ehp_total instead.",
    )
    sort: str = Field(
        default="dps_total", pattern="^(dps_total|dps_full|life_max|ehp_total|created_at)$"
    )
    limit: int = Field(default=5, ge=1, le=20)


async def _search_builds(ctx: ToolContext, a: SearchBuildsArgs) -> ToolResult:
    taxonomy = await ctx.builds.taxonomy(a.game.value)
    classes = {c["value"].lower() for c in taxonomy["classes"]}
    subclasses = {c["value"].lower() for c in taxonomy["subclasses"]}
    normalised: list[str] = []
    # Models confuse class and subclass; the corpus knows which is which.
    if a.subclass and a.subclass.lower() in classes and not a.class_name:
        a = a.model_copy(update={"class_name": a.subclass, "subclass": None})
        normalised.append(f"'{a.class_name}' is a class, moved to class_name")
    if a.class_name and a.class_name.lower() in subclasses and a.class_name.lower() not in classes:
        a = a.model_copy(update={"subclass": a.class_name, "class_name": None})
        normalised.append(f"'{a.subclass}' is a subclass, moved to subclass")
    skills = {c["value"].lower() for c in taxonomy["main_skills"]}
    for field_name in ("subclass", "class_name"):
        v = getattr(a, field_name)
        if v and v.lower() not in classes | subclasses and any(v.lower() in s for s in skills):
            a = a.model_copy(update={field_name: None, "main_skill": a.main_skill or v})
            normalised.append(f"'{v}' is a skill, moved to main_skill")
    q = BuildQuery(**{**a.model_dump(), "game": a.game.value})
    res = await search_builds(ctx.builds, q)
    items = []
    evidence: list[Evidence] = []
    for s in res.items:
        item = compact_snapshot(s)
        src = res.sources.get(s.id)
        item["source"] = (
            {"url": src.url, "title": src.title, "thread": src.parent_url} if src else None
        )
        item["label"] = _one_line(s, src.title if src else None, src.url if src else None)
        items.append(item)
        evidence.extend(metric_evidence(s, _label(s)))
    data: dict[str, Any] = {"total": res.total, "items": items, "filters_applied": q.__dict__}
    if normalised:
        data["normalised"] = normalised
    if res.total == 0:
        data["available_in_corpus"] = taxonomy
        data["hint"] = (
            "No match. Relax ONE filter using available_in_corpus (drop a threshold, widen the "
            "skill, or drop the subclass), say which one you dropped, and never invent a build."
        )
    return ToolResult(
        data=data,
        evidence=evidence,
        summary=(
            "no match"
            if res.total == 0
            else f"{res.total} match{'es' if res.total > 1 else ''}, showing {len(items)}"
        )
        + (f" ({'; '.join(normalised)})" if normalised else ""),
    )


class GetBuildArgs(BaseModel):
    snapshot_id: str


async def _get_build(ctx: ToolContext, a: GetBuildArgs) -> ToolResult:
    try:
        sid = uuid.UUID(a.snapshot_id)
    except ValueError as exc:
        raise ToolError(f"'{a.snapshot_id}' is not a snapshot id") from exc
    snapshot, source = await get_build(ctx.builds, sid)
    if snapshot is None:
        raise ToolError("no such snapshot in the corpus")
    data = compact_snapshot(snapshot)
    data["source"] = (
        {"url": source.url, "title": source.title, "thread": source.parent_url} if source else None
    )
    data["all_metrics"] = {m.key: _metric_view(m) for m in snapshot.metrics}
    return ToolResult(
        data=data, evidence=metric_evidence(snapshot, _label(snapshot)), summary=_label(snapshot)
    )


class AnalyzeCodeArgs(BaseModel):
    """No arguments: the tool reads the build code attached to the question. A model cannot be
    trusted to relay a 15 KB base64 blob — small ones try, and invent it."""


async def _analyze_code(ctx: ToolContext, a: AnalyzeCodeArgs) -> ToolResult:
    code = ctx.code
    if not code:
        raise ToolError("no build code is attached to the question; ask the user to attach one")
    try:
        s = analyze_code(code)
    except DomainError as exc:
        raise ToolError(f"{exc.code}: {exc}") from exc
    data = compact_snapshot(s)
    data["all_metrics"] = {m.key: _metric_view(m) for m in s.metrics}
    return ToolResult(data=data, evidence=metric_evidence(s, _label(s)), summary=_label(s))


class CalculateBuildArgs(BaseModel):
    modifications: list[Modification] = Field(
        min_length=1,
        description=(
            "Changes to apply inside the real engine. Kinds: tree.allocate {node_id}, "
            "tree.deallocate {node_id}, config.set {name, value}, gem.set_level {gem, level}, "
            "gem.set_quality {gem, quality}."
        ),
    )


def _variant_view(v: BuildVariant) -> dict:
    base = compact_snapshot(v.baseline) if v.baseline else None
    var = compact_snapshot(v.snapshot)
    deltas = {}
    if base:
        for k, after in var["metrics"].items():
            before = base["metrics"].get(k)
            if before and before["value"] is not None and after["value"] is not None:
                deltas[k] = {
                    "before": before["value"],
                    "after": after["value"],
                    "delta": after["value"] - before["value"],
                }
    return {
        "baseline": base,
        "variant": var,
        "deltas": deltas,
        "modifications": [m.model_dump() for m in v.modifications],
    }


async def _calculate_build(ctx: ToolContext, a: CalculateBuildArgs) -> ToolResult:
    code = ctx.code
    if not code:
        raise ToolError("no build code is attached to the question; ask the user to attach one")
    try:
        v = recalculate_code(code, a.modifications)
    except DomainError as exc:
        raise ToolError(f"{exc.code}: {exc}") from exc
    ev = metric_evidence(v.snapshot, "variant " + _label(v.snapshot))
    if v.baseline:
        ev += metric_evidence(v.baseline, "baseline " + _label(v.baseline))
    return ToolResult(
        data=_variant_view(v),
        evidence=ev,
        summary=f"recalculated with {_n(len(a.modifications), 'change')}",
    )


class CompareBuildsArgs(BaseModel):
    snapshot_ids: list[str] = Field(min_length=2, max_length=5)


async def _compare_builds(ctx: ToolContext, a: CompareBuildsArgs) -> ToolResult:
    snaps: list[BuildSnapshot] = []
    for sid in a.snapshot_ids:
        try:
            s, _ = await get_build(ctx.builds, uuid.UUID(sid))
        except ValueError as exc:
            raise ToolError(f"'{sid}' is not a snapshot id") from exc
        if s is None:
            raise ToolError(f"snapshot {sid} not in the corpus")
        snaps.append(s)
    games = {s.game for s in snaps}
    if len(games) > 1:
        raise ToolError("refusing to compare builds from different games")
    table = {}
    for k in HEADLINE:
        row = []
        for s in snaps:
            m = s.metric(k.value)
            row.append(None if m is None or m.value is None else m.value)
        if any(v is not None for v in row):
            first = row[0]
            table[k.value] = {
                "values": row,
                "delta_vs_first": [
                    None if (v is None or first is None) else v - first for v in row
                ],
            }
    ev: list[Evidence] = []
    for s in snaps:
        ev.extend(metric_evidence(s, _label(s)))
    return ToolResult(
        data={
            "builds": [compact_snapshot(s) for s in snaps],
            "table": table,
            "note": "None = unknown, not zero",
        },
        evidence=ev,
        summary=f"compared {len(snaps)} builds on {len(table)} numbers",
    )


class SearchKnowledgeArgs(BaseModel):
    game: GameId = Field(
        description="Game the question is about. PoE and PoE2 share names, not mechanics."
    )
    query: str = Field(min_length=2)
    k: int = Field(default=5, ge=1, le=20)
    patch: str | None = Field(default=None, description="Restrict to a patch, e.g. 3.29.")


async def _search_knowledge(ctx: ToolContext, a: SearchKnowledgeArgs) -> ToolResult:
    hits = await ctx.knowledge.search(a.game.value, a.query, k=a.k, patch=a.patch)
    data = [
        {
            "game": h.chunk.metadata.game,
            "patch": h.chunk.metadata.patch,
            "version": h.chunk.metadata.version,
            "title": h.title,
            "heading": h.heading,
            "published_at": h.chunk.metadata.published_at.isoformat()
            if h.chunk.metadata.published_at
            else None,
            "source_url": h.chunk.metadata.source_url,
            "excerpt": h.chunk.text[:600],
            "similarity": round(h.score, 3),
        }
        for h in hits
    ]
    return ToolResult(
        data=data,
        evidence=[knowledge_evidence(h) for h in hits],
        summary=f"{_n(len(hits), 'passage')} from the {game_name(a.game.value)} patch notes",
    )


class PatchChangesArgs(BaseModel):
    game: GameId
    patch: str | None = Field(default=None, description="e.g. 3.29; omit to list known patches.")
    topic: str | None = Field(default=None, description="Optional focus, e.g. a skill name.")


async def _get_patch_changes(ctx: ToolContext, a: PatchChangesArgs) -> ToolResult:
    patches = await ctx.knowledge.patches(a.game.value)
    if a.patch is None and a.topic and patches:
        # "What changed for X?" without a patch means the latest one; do not make the model
        # take a second round-trip to find that out.
        a = a.model_copy(update={"patch": patches[0]["patch"]})
    if a.patch is None:
        return ToolResult(
            data={
                "patches": [
                    {
                        **p,
                        "published_at": p["published_at"].isoformat()
                        if p["published_at"]
                        else None,
                    }
                    for p in patches
                ]
            },
            summary=f"{_n(len(patches), 'patch', 'patches')} known for {game_name(a.game.value)}",
        )
    if a.patch not in {p["patch"] for p in patches}:
        raise ToolError(
            f"no patch notes ingested for {a.game.value} {a.patch}; "
            f"known: {[p['patch'] for p in patches]}"
        )
    hits = await ctx.knowledge.search(a.game.value, a.topic or "changes", k=20, patch=a.patch)
    data = [
        {
            "heading": h.heading,
            "title": h.title,
            "excerpt": h.chunk.text[:600],
            "source_url": h.chunk.metadata.source_url,
        }
        for h in hits
    ]
    return ToolResult(
        data={
            "patch": a.patch,
            "known_patches": [p["patch"] for p in patches],
            "passages": data,
            "note": (
                "Passages are ranked by similarity to the topic; if none mentions it, say that "
                "nothing about it was found in this patch."
            ),
        },
        evidence=[knowledge_evidence(h) for h in hits],
        summary=f"{_n(len(hits), 'passage')} from {game_name(a.game.value)} {a.patch}",
    )


async def _corpus_stats(ctx: ToolContext, _: NoArgs) -> ToolResult:
    data = await corpus_stats(ctx.builds)
    return ToolResult(data=data, summary=f"{data['snapshots']} builds known")


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "list_games",
            "Games with an adapter and what each can honestly do (analyse, recalculate…).",
            NoArgs,
            _list_games,
        ),
        Tool(
            "search_builds",
            "Search the build corpus (public forum builds) with filters. Numbers come with "
            "provenance; None means unknown.",
            SearchBuildsArgs,
            _search_builds,
        ),
        Tool(
            "get_build", "Full detail of one corpus build by snapshot_id.", GetBuildArgs, _get_build
        ),
        Tool(
            "analyze_build_code",
            "Parse the build code attached to the question into a snapshot with provenance. "
            "Takes no arguments.",
            AnalyzeCodeArgs,
            _analyze_code,
        ),
        Tool(
            "calculate_build",
            "Apply modifications to the attached build inside the real engine and return "
            "baseline vs variant. Never approximates; may be unavailable.",
            CalculateBuildArgs,
            _calculate_build,
        ),
        Tool(
            "compare_builds",
            "Side-by-side headline metrics of 2–5 corpus builds of the same game, with deltas.",
            CompareBuildsArgs,
            _compare_builds,
        ),
        Tool(
            "search_knowledge",
            "Retrieve official patch-note passages for ONE game. Cite source_url and patch.",
            SearchKnowledgeArgs,
            _search_knowledge,
        ),
        Tool(
            "get_patch_changes",
            "List known patches for a game, or the passages of one patch (optionally focused "
            "on a topic).",
            PatchChangesArgs,
            _get_patch_changes,
        ),
        Tool(
            "corpus_stats",
            "How many builds the corpus holds per game and patch. Use it to say when the corpus "
            "is thin.",
            NoArgs,
            _corpus_stats,
        ),
    )
}


@dataclass
class ToolCallRecord:
    tool: str
    args: dict
    ok: bool
    summary: str
    duration_ms: int
    error: str | None = None


async def run_tool(
    ctx: ToolContext, name: str, raw_args: dict
) -> tuple[ToolResult | None, ToolCallRecord]:
    t0 = time.monotonic()
    tool = TOOLS.get(name)
    if tool is None:
        rec = ToolCallRecord(name, raw_args, False, "", 0, error=f"unknown tool '{name}'")
        return None, rec
    try:
        args = tool.args.model_validate(raw_args)
        result = await tool.run(ctx, args)
    except ToolError as exc:
        return None, ToolCallRecord(
            name, raw_args, False, "", int((time.monotonic() - t0) * 1000), error=str(exc)
        )
    except Exception as exc:  # validation or unexpected: the model must see a usable error
        return None, ToolCallRecord(
            name,
            raw_args,
            False,
            "",
            int((time.monotonic() - t0) * 1000),
            error=f"{type(exc).__name__}: {exc}"[:500],
        )
    return result, ToolCallRecord(
        name, raw_args, True, result.summary, int((time.monotonic() - t0) * 1000)
    )
