"""Ingest build codes from local files (one code per file) — dev seed and e2e fixture loader.

    .venv/bin/python scripts/ingest_files.py tests/fixtures/pob/*.txt

Files are recorded as ``kind=file`` sources with a ``file://`` URL; the fixtures README carries
the real attribution. Not a production path.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.corpus.pipeline import FetchedCode, ingest_many  # noqa: E402
from app.db.engine import dispose, init_db, session_factory  # noqa: E402
from app.db.repository import SourceRef  # noqa: E402


async def main(paths: list[str]) -> int:
    await init_db()
    fetched = [
        FetchedCode(
            code=Path(p).read_text(),
            source=SourceRef(
                kind="file",
                url=Path(p).resolve().as_uri(),
                game="poe",
                title=Path(p).stem,
                terms="local file (dev seed)",
            ),
        )
        for p in paths
    ]
    async with session_factory()() as session:
        report = await ingest_many(session, fetched)
    await dispose()
    print(
        f"ingested={report.ingested} duplicates={report.duplicates} rejected={len(report.rejected)}"
    )
    for url, why in report.rejected:
        print("  rejected", url, "—", why)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
