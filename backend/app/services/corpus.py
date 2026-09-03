"""Use cases over the corpus (SPEC § 7): the ``search_builds`` / ``get_build`` tools."""

from __future__ import annotations

import uuid

from app.domain.build import BuildSnapshot
from app.domain.ports import BuildQuery, BuildStore, SearchResult, SourceRef


async def search_builds(store: BuildStore, query: BuildQuery) -> SearchResult:
    return await store.search(query)


async def get_build(
    store: BuildStore, snapshot_id: uuid.UUID
) -> tuple[BuildSnapshot | None, SourceRef | None]:
    snapshot = await store.get_snapshot(snapshot_id)
    if snapshot is None:
        return None, None
    return snapshot, await store.get_source_of(snapshot_id)


async def corpus_stats(store: BuildStore) -> dict:
    return await store.stats()
