import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import ask, builds, corpus, games, knowledge, threads
from app.config import settings
from app.db.engine import dispose, init_db
from app.domain.errors import (
    DomainError,
    EngineUnavailable,
    InvalidBuildCode,
    InvalidModification,
    UnsupportedGame,
)
from app.knowledge.repository import GameFilterMissing


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Schema bootstrap is idempotent (ADR-009: create_all until Alembic). A missing database is a
    # degraded state the endpoints report themselves, not a reason to refuse to start.
    try:
        await init_db()
    except Exception as exc:  # pragma: no cover — depends on the environment
        logging.getLogger("reckoner").warning("database not initialised at startup: %s", exc)
    yield
    await dispose()


app = FastAPI(title="Reckoner", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATUS = {
    GameFilterMissing: 422,
    InvalidBuildCode: 422,
    InvalidModification: 422,
    UnsupportedGame: 404,
    EngineUnavailable: 503,
}


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    status = next((s for cls, s in _STATUS.items() if isinstance(exc, cls)), 400)
    return JSONResponse(status_code=status, content={"code": exc.code, "message": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(builds.router, prefix="/api/v1")
app.include_router(corpus.router, prefix="/api/v1")
app.include_router(games.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(ask.router, prefix="/api/v1")
app.include_router(threads.router, prefix="/api/v1")
