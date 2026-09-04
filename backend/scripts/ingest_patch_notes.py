"""Ingest official patch notes into the knowledge base (SPEC § 6).

    .venv/bin/python scripts/ingest_patch_notes.py --game poe --limit 5
    .venv/bin/python scripts/ingest_patch_notes.py --game poe2 --limit 5
    .venv/bin/python scripts/ingest_patch_notes.py --game wow --limit 5          # Blizzard news
    .venv/bin/python scripts/ingest_patch_notes.py --game wow_classic --limit 5  # Classic sections

Politeness and permissions: app/corpus/policy.py. Idempotent per thread URL.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.engine import dispose, init_db, session_factory  # noqa: E402
from app.knowledge.ingest import ingest_documents  # noqa: E402

FETCHERS = {
    "poe": "app.games.poe.sources.patch_notes",
    "poe2": "app.games.poe2.sources.patch_notes",
    "wow": "app.games.wow.sources.patch_notes",
    "wow_classic": "app.games.wow_classic.sources.patch_notes",
}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", choices=sorted(FETCHERS), required=True)
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()
    module = __import__(FETCHERS[args.game], fromlist=["patch_notes_fetcher"])
    fetcher = module.patch_notes_fetcher(limit=args.limit)

    await init_db()
    async with session_factory()() as session:
        report = await ingest_documents(session, fetcher)
    await dispose()
    print(f"documents={report.documents} chunks={report.chunks} skipped={len(report.skipped)}")
    for url, why in report.skipped:
        print("  skipped", url, "—", why)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
