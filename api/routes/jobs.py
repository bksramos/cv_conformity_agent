from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import JobListOut, JobOut
from database.connection import get_db
from database.repositories.jd_repository import JDRepository

router = APIRouter(tags=["Jobs"])

ACTIVE_WINDOW_DAYS = 14


def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=ACTIVE_WINDOW_DAYS)


def _is_active(scraped_at) -> bool:
    if scraped_at is None:
        return False
    if scraped_at.tzinfo is None:
        scraped_at = scraped_at.replace(tzinfo=timezone.utc)
    return scraped_at >= _cutoff()


def _to_job_out(o) -> JobOut:
    return JobOut(
        id                   = o.id,
        title                = o.title,
        company              = o.company or "",
        domain               = o.domain,
        seniority            = o.seniority,
        source               = o.source,
        source_url           = o.source_url,
        min_experience_years = o.structured_data.get("min_experience_years") if o.structured_data else None,
        extraction_confidence= o.extraction_confidence,
        scraped_at           = o.scraped_at,
    )


@router.get("/jobs", response_model=JobListOut, summary="Lista vagas do banco")
async def list_jobs(
    domain:         str | None = Query(None),
    seniority:      str | None = Query(None),
    limit:          int        = Query(50,    ge=1, le=500),
    offset:         int        = Query(0,     ge=0),
    show_archived:  bool       = Query(False, description="Inclui vagas extraídas há mais de 14 dias"),
    db: AsyncSession = Depends(get_db),
):
    repo = JDRepository(db)
    orms = await repo.list_active(
        domain=domain, seniority=seniority, limit=limit, offset=offset,
    )

    # Filtra por janela de tempo em Python — sem alterar schema do banco
    if not show_archived:
        orms = [o for o in orms if _is_active(o.scraped_at)]

    jobs = [_to_job_out(o) for o in orms]
    return JobListOut(total=len(jobs), jobs=jobs)


@router.get("/jobs/stats", summary="Estatísticas do banco de vagas")
async def jobs_stats(db: AsyncSession = Depends(get_db)):
    repo     = JDRepository(db)
    all_orms = await repo.list_active(limit=9999)

    active   = [o for o in all_orms if _is_active(o.scraped_at)]
    archived = [o for o in all_orms if not _is_active(o.scraped_at)]

    domain_counts: dict[str, int] = {}
    for o in active:
        dom = o.domain.value if hasattr(o.domain, "value") else str(o.domain)
        domain_counts[dom] = domain_counts.get(dom, 0) + 1

    last_scraped = max(
        (o.scraped_at for o in all_orms if o.scraped_at), default=None
    )

    return {
        "total":              len(all_orms),
        "active":             len(active),
        "archived":           len(archived),
        "by_domain":          domain_counts,
        "last_scraped_at":    last_scraped.isoformat() if last_scraped else None,
        "active_window_days": ACTIVE_WINDOW_DAYS,
        "cutoff":             _cutoff().isoformat(),
    }


@router.get("/jobs/{jd_id}", response_model=JobOut, summary="Detalhe de uma vaga")
async def get_job(jd_id: str, db: AsyncSession = Depends(get_db)):
    repo = JDRepository(db)
    orm  = await repo.get_by_id(UUID(jd_id))
    if not orm:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")
    return _to_job_out(orm)