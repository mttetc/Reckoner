"""Stored conversations for assistant-ui's remote thread list and history adapters."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import Conversations, Session
from app.domain.ports import StoredMessage, ThreadMeta
from app.services.conversations import append_message, create_thread, list_threads

router = APIRouter(prefix="/threads", tags=["threads"])


class ThreadView(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    created_at: Any
    last_message_at: Any


class ThreadPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, pattern="^(regular|archived)$")


class MessageIn(BaseModel):
    message: dict[str, Any]
    parent_id: str | None = None


class MessageView(BaseModel):
    id: str
    parent_id: str | None
    message: dict[str, Any]


def _view(t: ThreadMeta) -> ThreadView:
    return ThreadView(
        id=t.id,
        title=t.title,
        status=t.status,
        created_at=t.created_at,
        last_message_at=t.last_message_at,
    )


def _msg(m: StoredMessage) -> MessageView:
    return MessageView(id=m.id, parent_id=m.parent_id, message=m.message)


@router.get("", response_model=list[ThreadView])
async def index(store: Conversations) -> list[ThreadView]:
    return [_view(t) for t in await list_threads(store)]


@router.post("", response_model=ThreadView, status_code=201)
async def create(store: Conversations, session: Session) -> ThreadView:
    t = await create_thread(store)
    await session.commit()
    return _view(t)


@router.get("/{thread_id}", response_model=ThreadView)
async def show(thread_id: uuid.UUID, store: Conversations) -> ThreadView:
    t = await store.get_thread(thread_id)
    if t is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "no such thread"}
        )
    return _view(t)


@router.patch("/{thread_id}", response_model=ThreadView)
async def patch(
    thread_id: uuid.UUID, body: ThreadPatch, store: Conversations, session: Session
) -> ThreadView:
    t = await store.update_thread(thread_id, title=body.title, status=body.status)
    if t is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "no such thread"}
        )
    await session.commit()
    return _view(t)


@router.delete("/{thread_id}", status_code=204)
async def remove(thread_id: uuid.UUID, store: Conversations, session: Session) -> None:
    if not await store.delete_thread(thread_id):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "no such thread"}
        )
    await session.commit()


@router.get("/{thread_id}/messages", response_model=list[MessageView])
async def messages(thread_id: uuid.UUID, store: Conversations) -> list[MessageView]:
    if await store.get_thread(thread_id) is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "no such thread"}
        )
    return [_msg(m) for m in await store.messages(thread_id)]


@router.post("/{thread_id}/messages", response_model=MessageView, status_code=201)
async def append(
    thread_id: uuid.UUID, body: MessageIn, store: Conversations, session: Session
) -> MessageView:
    if await store.get_thread(thread_id) is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "no such thread"}
        )
    message_id = str(body.message.get("id") or uuid.uuid4())
    m = await append_message(store, thread_id, message_id, body.parent_id, body.message)
    await session.commit()
    return _msg(m)
