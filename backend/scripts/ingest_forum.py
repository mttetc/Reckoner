"""Ingest PoB codes linked from the official forums into the corpus (SPEC § 7).

    .venv/bin/python scripts/ingest_forum.py [--threads-per-forum 10] [--forums duelist,witch]

Polite by construction (app/corpus/policy.py): allowlisted hosts only, robots.txt honoured,
identified User-Agent, ≥ 2 s between requests per host. Run it from cron, not from the API.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.corpus.pipeline import ingest_many  # noqa: E402
from app.db.engine import dispose, init_db, session_factory  # noqa: E402
from app.games.poe.sources.forum import CLASS_FORUMS, ForumFetcher  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads-per-forum", type=int, default=10)
    ap.add_argument("--links-per-thread", type=int, default=2)
    ap.add_argument("--forums", default=",".join(CLASS_FORUMS))
    args = ap.parse_args()

    forums = {k: CLASS_FORUMS[k] for k in args.forums.split(",") if k in CLASS_FORUMS}
    fetcher = ForumFetcher(
        forums=forums,
        threads_per_forum=args.threads_per_forum,
        links_per_thread=args.links_per_thread,
    )
    await init_db()
    async with session_factory()() as session:
        report = await ingest_many(session, fetcher, game="poe")
    await dispose()
    print(
        f"ingested={report.ingested} duplicates={report.duplicates} "
        f"rejected={len(report.rejected)} skipped={len(fetcher.skipped)}"
    )
    for url, why in report.rejected:
        print("  rejected", url, "—", why)
    for url, why in fetcher.skipped[:20]:
        print("  skipped ", url, "—", why)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
