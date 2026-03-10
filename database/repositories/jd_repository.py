from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import JobDescriptionORM
from models.jd_model import JobDescription
from loguru import logger

class JDRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, jd_id: UUID) -> Optional[JobDescriptionORM]:
        result = await self.session.execute(
            select(JobDescriptionORM).where(JobDescriptionORM.id == jd_id)
        )
        return result.scalar_one_or_none()

    async def get_by_source_url(self, url: str) -> Optional[JobDescriptionORM]:
        result = await self.session.execute(
            select(JobDescriptionORM).where(JobDescriptionORM.source_url == url)
        )
        return result.scalar_one_or_none()

    async def exists_by_url(self, url: str) -> bool:
        return await self.get_by_source_url(url) is not None

    async def insert(self, jd: JobDescription, raw_text: str, source: str) -> JobDescriptionORM:
        orm = JobDescriptionORM(
            id=jd.id,
            title=jd.title,
            raw_text=raw_text,
            structured_data=jd.model_dump(mode="json"),
            domain=jd.domain.value,
            seniority=jd.seniority.value,
            source=source,
            source_url=str(jd.source_url) if jd.source_url else None,
            scraped_at=jd.scraped_at,
            extraction_confidence=jd.extraction_confidence,
        )
        self.session.add(orm)
        await self.session.flush()
        logger.info(f"[JDRepository] Inserted JD: {jd.title} ({source})")
        return orm

    async def list_active(
        self,
        domain: Optional[str] = None,
        seniority: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobDescriptionORM]:
        q = select(JobDescriptionORM).where(JobDescriptionORM.is_active == True)
        if domain:
            q = q.where(JobDescriptionORM.domain == domain)
        if seniority:
            q = q.where(JobDescriptionORM.seniority == seniority)
        q = q.order_by(JobDescriptionORM.scraped_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def deactivate_old(self, source: str, active_ids: list[UUID]) -> int:
        """Desativa JDs da source que não estão mais na lista de ativas."""
        result = await self.session.execute(
            update(JobDescriptionORM)
            .where(
                JobDescriptionORM.source == source,
                JobDescriptionORM.id.notin_(active_ids)
            )
            .values(is_active=False)
        )
        return result.rowcount

