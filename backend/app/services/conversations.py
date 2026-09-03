"""Use cases over stored conversations (assistant-ui thread list + history)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.domain.ports import ConversationStore, StoredMessage, ThreadMeta

TITLE_MAX = 60


def title_from(message: dict) -> str | None:
    """A thread title from the first user message: its text, trimmed, without pasted codes."""
    parts = message.get("content") or []
    text = " ".join(
        str(p.get("text", "")) for p in parts if isinstance(p, dict) and p.get("type") == "text"
    )
    import re

    text = re.sub(r"e[JN][A-Za-z0-9+/_=-]{200,}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Build analysis" if parts else None
    return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1].rstrip() + "…"


async def list_threads(store: ConversationStore) -> Sequence[ThreadMeta]:
    return await store.list_threads()


async def create_thread(store: ConversationStore) -> ThreadMeta:
    return await store.create_thread()


async def append_message(
    store: ConversationStore,
    thread_id: uuid.UUID,
    message_id: str,
    parent_id: str | None,
    message: dict,
) -> StoredMessage:
    stored = await store.append_message(thread_id, message_id, parent_id, message)
    thread = await store.get_thread(thread_id)
    if thread is not None and not thread.title and message.get("role") == "user":
        await store.update_thread(thread_id, title=title_from(message))
    return stored
