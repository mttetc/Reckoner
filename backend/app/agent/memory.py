"""Conversation memory for the agent: a LangGraph checkpointer keyed by ``thread_id``.

``agent_memory`` selects the store: ``postgres`` (default; the same database as the corpus,
tables created by LangGraph on first use), ``memory`` (process-local, tests), ``off``.
An unreachable store is a degraded state the answer reports; it never blocks an answer.
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.config import settings

# Our own types stored in the graph state. Anything else is refused at load time
# (LANGGRAPH_STRICT_MSGPACK semantics), so a checkpoint can never smuggle in arbitrary objects.
STATE_TYPES: tuple[tuple[str, str], ...] = (
    ("app.agent.tools", "ToolCallRecord"),
    ("app.domain.evidence", "Evidence"),
    ("app.domain.provenance", "Provenance"),
    ("app.domain.provenance", "ProvenanceStatus"),
    ("app.domain.build", "GameId"),
)


def serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES)


log = logging.getLogger("reckoner.agent.memory")

_saver: BaseCheckpointSaver | None = None
_pool = None


def _psycopg_url(url: str) -> str:
    # SQLAlchemy URL (postgresql+asyncpg://…) → libpq URL (postgresql://…)
    scheme, rest = url.split("://", 1)
    return scheme.split("+", 1)[0] + "://" + rest


async def get_checkpointer() -> BaseCheckpointSaver | None:
    """The configured checkpointer, created on first use. ``None`` when memory is off."""
    global _saver, _pool
    if settings.agent_memory == "off":
        return None
    if _saver is not None:
        return _saver
    if settings.agent_memory == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        _saver = InMemorySaver(serde=serializer())
        return _saver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        _psycopg_url(settings.database_url),
        open=False,
        min_size=1,
        max_size=settings.agent_memory_pool_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool, serde=serializer())
    await saver.setup()
    _pool, _saver = pool, saver
    return _saver


async def close_checkpointer() -> None:
    global _saver, _pool
    if _pool is not None:
        await _pool.close()
    _saver, _pool = None, None
