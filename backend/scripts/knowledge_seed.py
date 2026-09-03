"""Seed the knowledge base with the synthetic forum fixtures (e2e / dev). Both games, shared
vocabulary — exactly what the isolation test needs, with no official prose involved.

    .venv/bin/python scripts/knowledge_seed.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.engine import dispose, init_db, session_factory  # noqa: E402
from app.knowledge.chunker import chunk_post, first_post  # noqa: E402
from app.knowledge.ingest import ingest_documents  # noqa: E402
from app.knowledge.sources.ggg_forum import PatchNoteDocument  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "forum"
DOCS = [
    ("poe", "poe1_patch_notes.html", "3.29.0b Patch Notes (synthetic)", "3.29.0b", "3.29"),
    ("poe2", "poe2_patch_notes.html", "0.5.5 Patch Notes (synthetic)", "0.5.5", "0.5"),
]


async def main() -> int:
    await init_db()
    docs = []
    for game, name, title, version, patch in DOCS:
        post = first_post(html.fromstring((FIX / name).read_text()))
        assert post is not None
        docs.append(
            PatchNoteDocument(
                game=game,
                source="fixture:synthetic",
                source_url=f"fixture://{name}",
                title=title,
                version=version,
                patch=patch,
                published_at=None,
                chunks=chunk_post(post),
            )
        )
    async with session_factory()() as session:
        report = await ingest_documents(session, docs)
    await dispose()
    print(f"documents={report.documents} chunks={report.chunks} skipped={len(report.skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
