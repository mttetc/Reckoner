"""Read-only corpus endpoints. Ingestion is a script / cron concern, never an HTTP one."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import BuildDetail, BuildSummary, CorpusStats, SearchResponse, SourceInfo
from app.db.engine import get_session
from app.db.repository import BuildQuery, SourceRef
from app.domain.build import BuildSnapshot, GameId
from app.domain.provenance import MetricKey
from app.services.corpus import corpus_stats, get_build, search_builds

router = APIRouter(tags=["corpus"])

Session = Annotated[AsyncSession, Depends(get_session)]


def _summary(s: BuildSnapshot, source: SourceRef | None) -> BuildSummary:
    pick = (
        MetricKey.DPS_TOTAL,
        MetricKey.DPS_FULL,
        MetricKey.MINION_DPS_TOTAL,
        MetricKey.LIFE_MAX,
        MetricKey.ENERGY_SHIELD_MAX,
        MetricKey.EHP_TOTAL,
    )
    return BuildSummary(
        snapshot_id=s.id,
        game=s.game,
        game_version=s.game_version,
        character=s.character,
        main_skill=s.main_skill,
        metrics=[m for k in pick if (m := s.metric(k.value)) is not None],
        node_count=len(s.tree.node_ids) if s.tree.node_ids else None,
        created_at=s.created_at,
        source=_source(source),
    )


def _source(ref: SourceRef | None) -> SourceInfo | None:
    if ref is None:
        return None
    return SourceInfo(
        kind=ref.kind, url=ref.url, title=ref.title, parent_url=ref.parent_url, terms=ref.terms
    )


@router.get("/builds", response_model=SearchResponse)
async def list_builds(
    session: Session,
    game: GameId | None = None,
    class_name: str | None = None,
    subclass: str | None = None,
    main_skill: str | None = None,
    game_version: str | None = None,
    min_dps: float | None = Query(default=None, ge=0),
    min_life: float | None = Query(default=None, ge=0),
    min_ehp: float | None = Query(default=None, ge=0),
    sort: str = Query(
        default="dps_total", pattern="^(dps_total|dps_full|life_max|ehp_total|created_at)$"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    q = BuildQuery(
        game=game.value if game else None,
        class_name=class_name,
        subclass=subclass,
        main_skill=main_skill,
        game_version=game_version,
        min_dps=min_dps,
        min_life=min_life,
        min_ehp=min_ehp,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    result = await search_builds(session, q)
    return SearchResponse(
        total=result.total,
        items=[_summary(s, result.sources.get(s.id)) for s in result.items],
    )


@router.get("/builds/{snapshot_id}", response_model=BuildDetail)
async def build_detail(snapshot_id: uuid.UUID, session: Session) -> BuildDetail:
    snapshot, source = await get_build(session, snapshot_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "no such snapshot"}
        )
    return BuildDetail(snapshot=snapshot, source=_source(source))


@router.get("/corpus/stats", response_model=CorpusStats)
async def stats(session: Session) -> CorpusStats:
    return CorpusStats(**await corpus_stats(session))
