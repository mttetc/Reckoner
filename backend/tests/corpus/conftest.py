"""Corpus tests need PostgreSQL. They use a dedicated database and skip when none is reachable."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db import engine as db_engine
from app.db.models import Base

TEST_URL = settings.database_url.rsplit("/", 1)[0] + "/reckoner_test"


def _prepare() -> bool:
    async def go() -> bool:
        admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
        try:
            admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
            async with admin.connect() as conn:
                exists = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname='reckoner_test'")
                )
                if exists.scalar() is None:
                    await conn.execute(text("CREATE DATABASE reckoner_test"))
            await admin.dispose()
        except Exception as exc:  # pragma: no cover — diagnostics only
            import sys

            print(f"[corpus tests] database not usable: {exc!r}", file=sys.stderr)
            return False
        eng = create_async_engine(TEST_URL)
        async with eng.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()
        return True

    return asyncio.run(go())


DB_READY = _prepare()
pytestmark = pytest.mark.skipif(not DB_READY, reason="PostgreSQL not reachable")


@pytest_asyncio.fixture(loop_scope="function")
async def session():
    if not DB_READY:
        pytest.skip("PostgreSQL not reachable")
    db_engine.get_engine(TEST_URL)
    async with db_engine.session_factory()() as s:
        for table in reversed(Base.metadata.sorted_tables):
            await s.execute(text(f"TRUNCATE {table.name} CASCADE"))
        await s.commit()
        yield s
    await db_engine.dispose()
