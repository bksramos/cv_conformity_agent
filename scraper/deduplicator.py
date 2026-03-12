# ============================================================
# Evita inserir JDs duplicadas no banco
# ============================================================
from __future__ import annotations
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from database.repositories.jd_repository import JDRepository
from scraper.base_scraper import RawJob


class JobDeduplicator:
    """
    Verifica se uma vaga já existe no banco pelo source_url.
    Análogo ao controle de cache contamination do Feito/Conferido.
    """

    def __init__(self, session: AsyncSession):
        self._repo = JDRepository(session)
        self._seen_urls: set[str] = set()   # cache in-memory por execução

    async def is_duplicate(self, job: RawJob) -> bool:
        url = job.source_url

        # 1. Checa cache in-memory (evita hits duplos no banco na mesma execução)
        if url in self._seen_urls:
            logger.debug(f"[Deduplicator] Duplicado in-memory: {url}")
            return True

        # 2. Checa no banco
        exists = await self._repo.exists_by_url(url)
        if exists:
            logger.debug(f"[Deduplicator] Já existe no banco: {url}")
            self._seen_urls.add(url)
            return True

        # Marca como visto para esta execução
        self._seen_urls.add(url)
        return False

    async def filter_new(self, jobs: list[RawJob]) -> tuple[list[RawJob], int]:
        """
        Filtra lista de RawJobs retornando apenas as novas.
        Retorna: (novas_vagas, total_duplicadas)
        """
        new_jobs, duplicates = [], 0
        for job in jobs:
            if await self.is_duplicate(job):
                duplicates += 1
            else:
                new_jobs.append(job)

        logger.info(
            f"[Deduplicator] {len(new_jobs)} novas | {duplicates} duplicadas "
            f"(total recebido: {len(jobs)})"
        )
        return new_jobs, duplicates