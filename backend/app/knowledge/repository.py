"""Knowledge storage and game-filtered retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeChunkRow
from app.domain.errors import DomainError
from app.domain.knowledge import KnowledgeChunk, KnowledgeMetadata
from app.knowledge.chunker import Chunk
from app.knowledge.embedder import Embedder


class GameFilterMissing(DomainError):
    """Retrieval without a game is refused: PoE/PoE2 vocabulary collides (SPEC § 6)."""

    code = "game_filter_missing"


@dataclass(frozen=True)
class Hit:
    chunk: KnowledgeChunk
    heading: str | None
    title: str | None
    score: float  # cosine similarity, informational only


def _to_domain(row: KnowledgeChunkRow) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=str(row.id),
        text=row.text,
        metadata=KnowledgeMetadata(
            game=row.game,
            version=row.version,
            patch=row.patch,
            season=row.season,
            class_name=row.class_name,
            source=row.source,
            source_url=row.source_url,
            published_at=row.published_at,
            retrieved_at=row.retrieved_at,
        ),
    )


class KnowledgeRepository:
    def __init__(self, session: AsyncSession, embedder: Embedder) -> None:
        self.s = session
        self.embedder = embedder

    async def replace_document(
        self,
        *,
        game: str,
        source: str,
        source_url: str,
        title: str | None,
        chunks: list[Chunk],
        version: str | None = None,
        patch: str | None = None,
        season: str | None = None,
        class_name: str | None = None,
        published_at: datetime | None = None,
    ) -> int:
        """Idempotent per source_url: re-ingesting a page replaces its chunks."""
        await self.s.execute(
            delete(KnowledgeChunkRow).where(KnowledgeChunkRow.source_url == source_url)
        )
        if not chunks:
            return 0
        vectors = self.embedder.embed([f"{c.heading or title or ''}\n{c.text}" for c in chunks])
        for c, v in zip(chunks, vectors, strict=True):
            self.s.add(
                KnowledgeChunkRow(
                    game=game,
                    version=version,
                    patch=patch,
                    season=season,
                    class_name=class_name,
                    source=source,
                    source_url=source_url,
                    title=title,
                    heading=c.heading,
                    ordinal=c.ordinal,
                    text=c.text,
                    published_at=published_at,
                    embedder=self.embedder.name,
                    embedding=v,
                )
            )
        await self.s.flush()
        return len(chunks)

    async def search(
        self,
        game: str | None,
        query: str,
        *,
        k: int = 8,
        patch: str | None = None,
        source: str | None = None,
    ) -> list[Hit]:
        if not game:
            raise GameFilterMissing(
                "knowledge retrieval requires a game; refusing to search across games"
            )
        [qv] = self.embedder.embed([query])
        distance = KnowledgeChunkRow.embedding.cosine_distance(qv)
        stmt = select(KnowledgeChunkRow, distance.label("d")).where(KnowledgeChunkRow.game == game)
        if patch:
            stmt = stmt.where(KnowledgeChunkRow.patch == patch)
        if source:
            stmt = stmt.where(KnowledgeChunkRow.source == source)
        stmt = stmt.order_by(distance).limit(min(k, 50))
        rows = (await self.s.execute(stmt)).all()
        return [Hit(_to_domain(r), r.heading, r.title, 1.0 - float(d)) for r, d in rows]

    async def patches(self, game: str) -> list[dict]:
        stmt = (
            select(
                KnowledgeChunkRow.patch,
                func.min(KnowledgeChunkRow.published_at),
                func.count(),
                func.min(KnowledgeChunkRow.source_url),
            )
            .where(KnowledgeChunkRow.game == game, KnowledgeChunkRow.patch.is_not(None))
            .group_by(KnowledgeChunkRow.patch)
            .order_by(func.min(KnowledgeChunkRow.published_at).desc())
        )
        return [
            {"patch": p, "published_at": d, "chunks": n, "source_url": u}
            for p, d, n, u in (await self.s.execute(stmt)).all()
        ]

    async def stats(self) -> dict:
        rows = (
            await self.s.execute(
                select(KnowledgeChunkRow.game, KnowledgeChunkRow.embedder, func.count()).group_by(
                    KnowledgeChunkRow.game, KnowledgeChunkRow.embedder
                )
            )
        ).all()
        per_game: dict[str, int] = {}
        for g, _, n in rows:
            per_game[g] = per_game.get(g, 0) + n
        return {
            "chunks": sum(n for _, _, n in rows),
            "per_game": per_game,
            "embedders": sorted({e for _, e, _ in rows}),
        }
