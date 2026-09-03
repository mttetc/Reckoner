"""Use cases over knowledge: the ``search_knowledge`` / ``get_patch_changes`` tools."""

from __future__ import annotations

from app.domain.ports import Hit, KnowledgeStore


async def search_knowledge(
    store: KnowledgeStore, game: str, query: str, *, k: int = 8, patch: str | None = None
) -> list[Hit]:
    return await store.search(game, query, k=k, patch=patch)


async def list_patches(store: KnowledgeStore, game: str) -> list[dict]:
    return await store.patches(game)


async def knowledge_stats(store: KnowledgeStore) -> dict:
    return await store.stats()
