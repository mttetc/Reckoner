"""Ports: what the application needs from the outside world, stated as Protocols.

The domain and the services depend on these; ``app.db`` and ``app.knowledge`` implement them
with PostgreSQL. Nothing here imports a framework — the architecture test enforces it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.domain.build import BuildSnapshot
from app.domain.knowledge import KnowledgeChunk

# ---------------------------------------------------------------- builds


@dataclass(frozen=True)
class SourceRef:
    kind: str
    url: str
    game: str
    title: str | None = None
    parent_url: str | None = None
    terms: str | None = None


@dataclass(frozen=True)
class BuildQuery:
    game: str | None = None
    class_name: str | None = None
    subclass: str | None = None
    main_skill: str | None = None
    game_version: str | None = None
    min_dps: float | None = None
    min_life: float | None = None
    min_ehp: float | None = None
    sort: str = "dps_total"
    limit: int = 20
    offset: int = 0


@dataclass
class SearchResult:
    total: int
    items: list[BuildSnapshot] = field(default_factory=list)
    sources: dict[uuid.UUID, SourceRef] = field(default_factory=dict)


class BuildStore(Protocol):
    async def find_by_hash(self, game: str, raw_sha256: str) -> Any: ...
    async def upsert_source(self, ref: SourceRef) -> Any: ...
    async def add_snapshot(
        self,
        snapshot: BuildSnapshot,
        source: Any = None,
        build_id: uuid.UUID | None = None,
        name: str | None = None,
    ) -> Any: ...
    async def get_snapshot(self, snapshot_id: uuid.UUID) -> BuildSnapshot | None: ...
    async def get_source_of(self, snapshot_id: uuid.UUID) -> SourceRef | None: ...
    async def search(self, q: BuildQuery) -> SearchResult: ...
    async def taxonomy(self, game: str) -> dict: ...
    async def stats(self) -> dict: ...


# ---------------------------------------------------------------- knowledge


@dataclass(frozen=True)
class Hit:
    chunk: KnowledgeChunk
    heading: str | None
    title: str | None
    score: float


class KnowledgeStore(Protocol):
    async def search(
        self,
        game: str | None,
        query: str,
        *,
        k: int = 8,
        patch: str | None = None,
        source: str | None = None,
    ) -> list[Hit]: ...
    async def patches(self, game: str) -> list[dict]: ...
    async def stats(self) -> dict: ...


# ---------------------------------------------------------------- conversations


@dataclass(frozen=True)
class ThreadMeta:
    id: uuid.UUID
    title: str | None
    status: str  # regular | archived
    created_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True)
class StoredMessage:
    id: str
    parent_id: str | None
    message: dict[str, Any]  # the client's message object, stored verbatim
    created_at: datetime


class ConversationStore(Protocol):
    async def list_threads(self, *, include_archived: bool = True) -> Sequence[ThreadMeta]: ...
    async def create_thread(self, thread_id: uuid.UUID | None = None) -> ThreadMeta: ...
    async def get_thread(self, thread_id: uuid.UUID) -> ThreadMeta | None: ...
    async def update_thread(
        self, thread_id: uuid.UUID, *, title: str | None = None, status: str | None = None
    ) -> ThreadMeta | None: ...
    async def delete_thread(self, thread_id: uuid.UUID) -> bool: ...
    async def messages(self, thread_id: uuid.UUID) -> Sequence[StoredMessage]: ...
    async def append_message(
        self, thread_id: uuid.UUID, message_id: str, parent_id: str | None, message: dict
    ) -> StoredMessage: ...


class FeedbackStore(Protocol):
    async def record(
        self, message_id: str, rating: str, question: str | None, answer: str | None
    ) -> None: ...
