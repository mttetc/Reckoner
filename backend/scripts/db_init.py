"""Create the database (if missing), the pgvector extension and the tables.

    .venv/bin/python scripts/db_init.py            # uses RECKONER_DATABASE_URL
    .venv/bin/python scripts/db_init.py --reset    # drop and recreate the tables (dev / e2e only)

ADR-009: ``create_all`` until Alembic is needed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db.engine import dispose, get_engine, init_db  # noqa: E402
from app.db.models import Base  # noqa: E402


async def ensure_database(url: str) -> None:
    base, name = url.rsplit("/", 1)
    admin = create_async_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{name}"'))
                print(f"created database {name}")
    finally:
        await admin.dispose()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    args = ap.parse_args()

    await ensure_database(settings.database_url)
    engine = get_engine()
    if args.reset:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await init_db(engine)
    await dispose()
    print(
        f"schema ready on {settings.database_url.split('@')[-1]}{' (reset)' if args.reset else ''}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
