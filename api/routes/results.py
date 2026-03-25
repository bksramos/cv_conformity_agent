from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import ConformityResultOut, DimensionsOut, DimensionScoreOut
from database.connection import get_db
from database.models import AnalysisResultORM
from database.repositories.result_repository import ResultRepository
from sqlalchemy import select

router = APIRouter(tags=["Results"])


@router.get("/results/{cv_hash}", summary="Histórico de análises de um CV")
async def get_results_by_cv(cv_hash: str, db: AsyncSession = Depends(get_db)):
    repo = ResultRepository(db)
    orms = await repo.get_by_cv_hash(cv_hash)
    if not orms:
        raise HTTPException(status_code=404, detail="Nenhuma análise encontrada para este CV")
    return {"cv_hash": cv_hash, "total": len(orms), "results": [
        {
            "id":            str(o.id),
            "jd_id":         str(o.jd_id),
            "verdict":       o.verdict,
            "overall_score": o.overall_score,
            "analyzed_at":   o.analyzed_at,
        }
        for o in orms
    ]}
