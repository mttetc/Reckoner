"""Documents in, chunks with mandatory game metadata out."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.embedder import Embedder, get_embedder
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.sources.ggg_forum import PatchNoteDocument


@dataclass
class KnowledgeReport:
    documents: int = 0
    chunks: int = 0
    skipped: list[tuple[str, str]] = field(default_factory=list)


async def ingest_documents(
    session: AsyncSession,
    documents: Iterable[PatchNoteDocument],
    embedder: Embedder | None = None,
) -> KnowledgeReport:
    repo = KnowledgeRepository(session, embedder or get_embedder())
    report = KnowledgeReport()
    for doc in documents:
        if not doc.game:
            report.skipped.append((doc.source_url, "document without game tag"))
            continue
        if not doc.chunks:
            report.skipped.append((doc.source_url, "no text extracted"))
            continue
        try:
            n = await repo.replace_document(
                game=doc.game,
                source=doc.source,
                source_url=doc.source_url,
                title=doc.title,
                chunks=doc.chunks,
                version=doc.version,
                patch=doc.patch,
                published_at=doc.published_at,
            )
        except Exception as exc:  # one bad page never aborts the batch
            await session.rollback()
            report.skipped.append((doc.source_url, f"{type(exc).__name__}: {exc}"))
            continue
        await session.commit()
        report.documents += 1
        report.chunks += n
    return report
