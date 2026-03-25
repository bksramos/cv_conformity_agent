from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from database.models import AnalysisResultORM
from models.conformity_result import ConformityResult
from loguru import logger


class ResultRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, result: ConformityResult) -> AnalysisResultORM:
        orm = AnalysisResultORM(
            id=result.id,
            cv_hash=result.cv_hash,
            jd_id=result.jd_id,
            candidate_name=result.candidate_name,
            verdict=result.verdict.value,
            overall_score=result.overall_score,
            has_absolute_blocker=result.has_absolute_blocker,
            dimensions_data=result.dimensions.model_dump() if result.dimensions else None,
            critical_gaps=result.critical_gaps,
            strengths=result.strengths,
            partial_matches=result.partial_matches,
            parecer_pt=result.parecer_final_pt,
            parecer_en=result.parecer_final_en,
            model_used=result.llm_model_used,
        )
        self.session.add(orm)
        await self.session.flush()
        logger.debug(f"[ResultRepository] Resultado salvo: {result.verdict.value} score={result.overall_score}")
        return orm

    async def get_by_cv_hash(self, cv_hash: str) -> list[AnalysisResultORM]:
        result = await self.session.execute(
            select(AnalysisResultORM)
            .where(AnalysisResultORM.cv_hash == cv_hash)
            .order_by(AnalysisResultORM.analyzed_at.desc())
        )
        return list(result.scalars().all())


