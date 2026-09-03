"""Read-only knowledge endpoints. ``game`` is required on retrieval — by type, not by convention."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import KnowledgeHit, KnowledgeStats, PatchInfo
from app.db.engine import get_session
from app.domain.build import GameId
from app.services.knowledge import knowledge_stats, list_patches, search_knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/search", response_model=list[KnowledgeHit])
async def search(
    session: Session,
    game: GameId,
    q: str = Query(min_length=2, max_length=500),
    k: int = Query(default=8, ge=1, le=50),
    patch: str | None = None,
) -> list[KnowledgeHit]:
    hits = await search_knowledge(session, game.value, q, k=k, patch=patch)
    return [
        KnowledgeHit(chunk=h.chunk, heading=h.heading, title=h.title, score=round(h.score, 4))
        for h in hits
    ]


@router.get("/patches", response_model=list[PatchInfo])
async def patches(session: Session, game: GameId) -> list[PatchInfo]:
    return [PatchInfo(**p) for p in await list_patches(session, game.value)]


@router.get("/stats", response_model=KnowledgeStats)
async def stats(session: Session) -> KnowledgeStats:
    return KnowledgeStats(**await knowledge_stats(session))
