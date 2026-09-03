from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import builds, games
from app.config import settings
from app.domain.errors import (
    DomainError,
    EngineUnavailable,
    InvalidBuildCode,
    InvalidModification,
    UnsupportedGame,
)

app = FastAPI(title="Reckoner", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATUS = {
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
app.include_router(games.router, prefix="/api/v1")
