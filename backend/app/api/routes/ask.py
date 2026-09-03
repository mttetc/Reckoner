"""Natural-language entry point (SPEC § 9 / § 10). The user never picks a tool."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import AgentAnswer
from app.agent.runner import ask as run_agent
from app.api.schemas import AskRequest, AskResponse, AuditView, FeedbackRequest, StepView
from app.db.engine import get_session
from app.db.models import FeedbackRow

router = APIRouter(tags=["ask"])
Session = Annotated[AsyncSession, Depends(get_session)]


def _to_response(a: AgentAnswer) -> AskResponse:
    return AskResponse(
        suggestions=a.suggestions,
        answer=a.text,
        model=a.model,
        steps=[
            StepView(
                tool=s.tool,
                args=s.args,
                ok=s.ok,
                summary=s.summary,
                error=s.error,
                duration_ms=s.duration_ms,
            )
            for s in a.steps
        ],
        evidence=a.evidence,
        audit=AuditView(
            checked=a.audit.checked, unverified=a.audit.unverified, clean=a.audit.clean
        ),
        degraded=a.degraded,
        input_tokens=a.input_tokens,
        output_tokens=a.output_tokens,
        duration_ms=a.duration_ms,
    )


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, session: Session) -> AskResponse:
    a = await run_agent(
        session, req.question, game=req.game.value if req.game else None, code=req.code
    )
    return _to_response(a)


@router.post("/ask/stream")
async def ask_stream(req: AskRequest, session: Session) -> StreamingResponse:
    """Server-sent events: step_start / step_end while tools run, then `done` with the answer."""
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    async def worker() -> None:
        try:
            a = await run_agent(
                session,
                req.question,
                game=req.game.value if req.game else None,
                code=req.code,
                on_event=on_event,
            )
            await queue.put({"type": "done", "response": _to_response(a).model_dump(mode="json")})
        except Exception as exc:  # the stream must end with something the client can show
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    async def events() -> AsyncIterator[str]:
        task = asyncio.create_task(worker())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/feedback", status_code=204)
async def feedback(req: FeedbackRequest, session: Session) -> None:
    """Thumbs up / down on an answer. Stored as-is; read by humans, never fed back to the model."""
    session.add(
        FeedbackRow(
            message_id=req.message_id, rating=req.rating, question=req.question, answer=req.answer
        )
    )
    await session.commit()
