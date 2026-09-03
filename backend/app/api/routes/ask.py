"""Natural-language entry point (SPEC § 9 / § 10). The user never picks a tool."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import ask as run_agent
from app.api.schemas import AskRequest, AskResponse, AuditView, StepView
from app.db.engine import get_session

router = APIRouter(tags=["ask"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, session: Session) -> AskResponse:
    a = await run_agent(
        session, req.question, game=req.game.value if req.game else None, code=req.code
    )
    return AskResponse(
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
