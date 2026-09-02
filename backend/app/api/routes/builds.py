from fastapi import APIRouter

from app.api.schemas import AnalyzeRequest, AnalyzeResponse
from app.services.analyze import analyze_code

router = APIRouter(prefix="/builds", tags=["builds"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    return AnalyzeResponse(snapshot=analyze_code(req.code, req.game))
