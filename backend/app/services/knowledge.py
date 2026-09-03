"""Use cases over knowledge: the future ``search_knowledge`` / ``get_patch_changes`` tools."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.embedder import get_embedder
from app.knowledge.repository import Hit, KnowledgeRepository


async def search_knowledge(
    session: AsyncSession, game: str, query: str, *, k: int = 8, patch: str | None = None
) -> list[Hit]:
    return await KnowledgeRepository(session, get_embedder()).search(game, query, k=k, patch=patch)


async def list_patches(session: AsyncSession, game: str) -> list[dict]:
    return await KnowledgeRepository(session, get_embedder()).patches(game)


async def knowledge_stats(session: AsyncSession) -> dict:
    return await KnowledgeRepository(session, get_embedder()).stats()
