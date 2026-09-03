"""Deterministic tools exposed to the model. Each returns JSON-able data plus Evidence."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BuildQuery
from app.domain.build import BuildSnapshot, BuildVariant, GameId, Modification
from app.domain.errors import DomainError
from app.domain.evidence import Evidence
from app.domain.provenance import Metric, MetricKey, Provenance, ProvenanceStatus
from app.games import list_adapters
from app.knowledge.embedder import get_embedder
from app.knowledge.repository import Hit, KnowledgeRepository
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
    session: AsyncSession
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
    return {
        "snapshot_id": str(s.id),
        "game": s.game.value,
        "game_version": s.game_version,
        "character": s.character.model_dump(),
        "main_skill": s.main_skill,
        "main_skill_links": [g.name for g in main_group.gems] if main_group else [],
        "metrics": {
            k.value: _metric_view(m) for k in HEADLINE if (m := s.metric(k.value)) is not None
        },
        "tree_nodes": len(s.tree.node_ids) if s.tree.node_ids else None,
        "items": [it.name or it.base_type for it in s.items if it.name or it.base_type],
    }


def metric_evidence(s: BuildSnapshot, label: str) -> list[Evidence]:
    out: list[Evidence] = []
    for k in HEADLINE:
        m = s.metric(k.value)
        if m is None or m.value is None or m.provenance is None:
            continue
        out.append(
            Evidence(
                statement=f"{label}: {k.value} = {m.value:g}{(' ' + m.unit) if m.unit else ''}",
                provenance=m.provenance,
            )
        )
    return out


def _label(s: BuildSnapshot) -> str:
    c = s.character
    return f"{c.class_name or '?'}{' ' + c.subclass if c.subclass else ''} · {s.main_skill or '?'}"


def knowledge_evidence(h: Hit) -> Evidence:
    md = h.chunk.metadata
    return Evidence(
        statement=f"{md.game} patch {md.patch or '?'} — {h.heading or h.title or md.source}",
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
    return ToolResult(data=data, summary=f"{len(data)} game(s) with adapters")


class SearchBuildsArgs(BaseModel):
    game: GameId = Field(description="Game the builds belong to. Never mix games.")
    class_name: str | None = Field(default=None, description="Base class, e.g. Duelist.")
    subclass: str | None = Field(default=None, description="Specialisation, e.g. Slayer.")
    main_skill: str | None = Field(default=None, description="Substring of the main skill name.")
    game_version: str | None = Field(default=None, description="Patch, e.g. 3.29.")
    min_dps: float | None = None
    min_life: float | None = None
    min_ehp: float | None = None
    sort: str = Field(
        default="dps_total", pattern="^(dps_total|dps_full|life_max|ehp_total|created_at)$"
    )
    limit: int = Field(default=5, ge=1, le=20)


async def _search_builds(ctx: ToolContext, a: SearchBuildsArgs) -> ToolResult:
    q = BuildQuery(**{**a.model_dump(), "game": a.game.value})
    res = await search_builds(ctx.session, q)
    items = []
    evidence: list[Evidence] = []
    for s in res.items:
        item = compact_snapshot(s)
        src = res.sources.get(s.id)
        item["source"] = (
            {"url": src.url, "title": src.title, "thread": src.parent_url} if src else None
        )
        items.append(item)
        evidence.extend(metric_evidence(s, _label(s)))
    return ToolResult(
        data={"total": res.total, "items": items},
        evidence=evidence,
        summary=f"{res.total} match(es), returned {len(items)}",
    )


class GetBuildArgs(BaseModel):
    snapshot_id: str


async def _get_build(ctx: ToolContext, a: GetBuildArgs) -> ToolResult:
    try:
        sid = uuid.UUID(a.snapshot_id)
    except ValueError as exc:
        raise ToolError(f"'{a.snapshot_id}' is not a snapshot id") from exc
    snapshot, source = await get_build(ctx.session, sid)
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
    code: str | None = Field(
        default=None,
        description="Build code. Omit to use the code the user pasted with the question.",
    )


async def _analyze_code(ctx: ToolContext, a: AnalyzeCodeArgs) -> ToolResult:
    code = a.code or ctx.code
    if not code:
        raise ToolError("no build code was provided with the question")
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
    code: str | None = Field(default=None, description="Build code; defaults to the pasted one.")


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
    code = a.code or ctx.code
    if not code:
        raise ToolError("no build code to recalculate; ask the user for their code")
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
        summary=f"{len(a.modifications)} modification(s) applied by the engine",
    )


class CompareBuildsArgs(BaseModel):
    snapshot_ids: list[str] = Field(min_length=2, max_length=5)


async def _compare_builds(ctx: ToolContext, a: CompareBuildsArgs) -> ToolResult:
    snaps: list[BuildSnapshot] = []
    for sid in a.snapshot_ids:
        try:
            s, _ = await get_build(ctx.session, uuid.UUID(sid))
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
        summary=f"compared {len(snaps)} builds on {len(table)} metrics",
    )


class SearchKnowledgeArgs(BaseModel):
    game: GameId = Field(
        description="Game the question is about. PoE and PoE2 share names, not mechanics."
    )
    query: str = Field(min_length=2)
    k: int = Field(default=5, ge=1, le=20)
    patch: str | None = Field(default=None, description="Restrict to a patch, e.g. 3.29.")


async def _search_knowledge(ctx: ToolContext, a: SearchKnowledgeArgs) -> ToolResult:
    repo = KnowledgeRepository(ctx.session, get_embedder())
    hits = await repo.search(a.game.value, a.query, k=a.k, patch=a.patch)
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
        summary=f"{len(hits)} passage(s) from {a.game.value} knowledge",
    )


class PatchChangesArgs(BaseModel):
    game: GameId
    patch: str | None = Field(default=None, description="e.g. 3.29; omit to list known patches.")
    topic: str | None = Field(default=None, description="Optional focus, e.g. a skill name.")


async def _get_patch_changes(ctx: ToolContext, a: PatchChangesArgs) -> ToolResult:
    repo = KnowledgeRepository(ctx.session, get_embedder())
    patches = await repo.patches(a.game.value)
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
            summary=f"{len(patches)} patch(es) known for {a.game.value}",
        )
    if a.patch not in {p["patch"] for p in patches}:
        raise ToolError(
            f"no patch notes ingested for {a.game.value} {a.patch}; "
            f"known: {[p['patch'] for p in patches]}"
        )
    hits = await repo.search(a.game.value, a.topic or "changes", k=20, patch=a.patch)
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
        data={"patch": a.patch, "passages": data},
        evidence=[knowledge_evidence(h) for h in hits],
        summary=f"{len(hits)} passage(s) for {a.game.value} {a.patch}",
    )


async def _corpus_stats(ctx: ToolContext, _: NoArgs) -> ToolResult:
    data = await corpus_stats(ctx.session)
    return ToolResult(data=data, summary=f"{data['snapshots']} snapshot(s) in the corpus")


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
            "Parse the build code the user pasted (or one given) into a snapshot with provenance.",
            AnalyzeCodeArgs,
            _analyze_code,
        ),
        Tool(
            "calculate_build",
            "Apply modifications to a build inside the real engine and return baseline vs "
            "variant. Never approximates; may be unavailable.",
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
        await ctx.session.rollback()
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
