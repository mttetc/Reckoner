"""Use cases over the corpus (SPEC § 7): the future ``search_builds`` / ``get_build`` tools."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BuildQuery, CorpusRepository, SearchResult, SourceRef
from app.domain.build import BuildSnapshot


async def search_builds(session: AsyncSession, query: BuildQuery) -> SearchResult:
    return await CorpusRepository(session).search(query)


async def get_build(
    session: AsyncSession, snapshot_id: uuid.UUID
) -> tuple[BuildSnapshot | None, SourceRef | None]:
    repo = CorpusRepository(session)
    snapshot = await repo.get_snapshot(snapshot_id)
    if snapshot is None:
        return None, None
    return snapshot, await repo.get_source_of(snapshot_id)


async def corpus_stats(session: AsyncSession) -> dict:
    return await CorpusRepository(session).stats()
