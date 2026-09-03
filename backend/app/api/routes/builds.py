from fastapi import APIRouter

from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    RecalculateRequest,
    RecalculateResponse,
)
from app.services.analyze import analyze_code
from app.services.recalculate import recalculate_code

router = APIRouter(prefix="/builds", tags=["builds"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    return AnalyzeResponse(snapshot=analyze_code(req.code, req.game))


@router.post(
    "/recalculate",
    response_model=RecalculateResponse,
    responses={
        503: {"description": "No headless engine configured — nothing is approximated."},
        422: {"description": "A modification cannot be applied as stated."},
    },
)
def recalculate(req: RecalculateRequest) -> RecalculateResponse:
    return RecalculateResponse(variant=recalculate_code(req.code, req.modifications, req.game))
