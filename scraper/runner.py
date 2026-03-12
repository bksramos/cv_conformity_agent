# ============================================================
# Orquestra um ciclo completo de scraping:
# Scrapers → Normalizer → Deduplicator → LLM → Banco
# ============================================================
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Type

from loguru import logger

from config.settings import settings
from config.feature_flags import flags
from scraper.base_scraper import BaseScraper, RawJob, ScraperResult
from scraper.normalizer import JobNormalizer
from scraper.deduplicator import JobDeduplicator
from scraper.sources.gupy_scraper import GupyScraper
from scraper.sources.remoteok_scraper import RemoteOKScraper
from agents.jd_extraction_agent import JDExtractionAgent
from database.connection import AsyncSessionLocal
from database.repositories.jd_repository import JDRepository
from database.models import ScrapingLogORM


# Mapa de scrapers disponíveis — adicionar novas fontes aqui
SCRAPER_REGISTRY: dict[str, Type[BaseScraper]] = {
    "gupy": GupyScraper,
    "remoteok": RemoteOKScraper,
}


class ScraperRunner:
    """
    Orquestrador do pipeline de scraping.
    Análogo ao pipeline de extração do Feito/Conferido.
    """

    def __init__(self, extraction_limit: int | None = None):
        self._normalizer = JobNormalizer()
        self._extraction_limit = extraction_limit

    async def run_all(self) -> dict[str, dict]:
        """Executa todos os scrapers habilitados via feature flags."""
        enabled = [
            name for name in SCRAPER_REGISTRY
            if flags.is_scraper_enabled(name)
        ]

        if not enabled:
            logger.warning("[Runner] Nenhum scraper habilitado nas feature flags.")
            return {}

        logger.info(f"[Runner] ▶ Iniciando ciclo de scraping — fontes: {enabled}")
        start = datetime.utcnow()
        summary = {}

        # Roda cada scraper sequencialmente para respeitar rate limits
        for name in enabled:
            try:
                stats = await self._run_scraper(name)
                summary[name] = stats
            except Exception as e:
                logger.error(f"[Runner] Falha crítica no scraper '{name}': {e}")
                summary[name] = {"status": "FAILED", "error": str(e)}

        total_secs = (datetime.utcnow() - start).total_seconds()
        total_inserted = sum(s.get("inserted", 0) for s in summary.values())
        logger.info(
            f"[Runner] ✅ Ciclo completo em {total_secs:.1f}s — "
            f"{total_inserted} novas vagas inseridas no total"
        )
        return summary

    async def _run_scraper(self, name: str) -> dict:
        """
        Pipeline completo para uma fonte:
        1. Fetch raw jobs
        2. Deduplica
        3. Extrai via LLM
        4. Persiste no banco
        5. Registra log
        """
        ScraperClass = SCRAPER_REGISTRY[name]
        stats = {
            "source": name,
            "found": 0,
            "duplicated": 0,
            "inserted": 0,
            "failed": 0,
            "status": "SUCCESS",
        }

        # --- 1. Fetch ---
        async with ScraperClass() as scraper:
            result: ScraperResult = await scraper.fetch_jobs()

        stats["found"] = result.total_found
        if result.errors:
            stats["errors"] = result.errors

        if not result.jobs:
            logger.info(f"[Runner][{name}] Nenhuma vaga encontrada.")
            stats["status"] = "PARTIAL" if result.errors else "SUCCESS"
            await self._save_log(stats, result)
            return stats

        # --- 2. Deduplica + 3. Extrai + 4. Persiste ---
        async with AsyncSessionLocal() as session:
            deduplicator = JobDeduplicator(session)
            repo = JDRepository(session)

            new_jobs, duplicated = await deduplicator.filter_new(result.jobs)
            stats["duplicated"] = duplicated

            # Aplica limite de extração (útil para testes locais com LLM lento)
            if self._extraction_limit:
                new_jobs = new_jobs[:self._extraction_limit]
                logger.info(f"[Runner][{name}] Limite de extração aplicado: {len(new_jobs)} vagas")

            if not new_jobs:
                logger.info(f"[Runner][{name}] Todas as vagas já existem no banco.")
                await session.commit()
                await self._save_log(stats, result)
                return stats

            logger.info(f"[Runner][{name}] Extraindo {len(new_jobs)} novas vagas via LLM...")

            async with JDExtractionAgent() as extractor:
                sem = asyncio.Semaphore(1)  # GPU processa 1 por vez mas muito mais rápido

                async def extract_and_save(raw_job: RawJob):
                    async with sem:
                        try:
                            jd = await extractor.extract(raw_job)
                            if jd is None:
                                stats["failed"] += 1
                                return

                            # Pula JDs com baixa confiança se flag estiver off
                            if (
                                not flags.PERSIST_LOW_CONFIDENCE_JDS
                                and jd.extraction_confidence < 0.4
                            ):
                                logger.warning(
                                    f"[Runner][{name}] Baixa confiança ignorada: "
                                    f"'{jd.title}' ({jd.extraction_confidence:.2f})"
                                )
                                stats["failed"] += 1
                                return

                            await repo.insert(jd, raw_job.raw_text, name)
                            stats["inserted"] += 1

                        except Exception as e:
                            logger.error(
                                f"[Runner][{name}] Erro ao processar "
                                f"'{raw_job.title}': {e}"
                            )
                            stats["failed"] += 1

                tasks = [extract_and_save(job) for job in new_jobs]
                await asyncio.gather(*tasks)

            await session.commit()

        if stats["failed"] > 0:
            stats["status"] = "PARTIAL"

        await self._save_log(stats, result)
        logger.info(
            f"[Runner][{name}] ✅ {stats['inserted']} inseridas | "
            f"{stats['duplicated']} duplicadas | {stats['failed']} falhas"
        )
        return stats

    async def _save_log(self, stats: dict, result: ScraperResult):
        """Persiste o log de execução do scraper no banco."""
        try:
            async with AsyncSessionLocal() as session:
                log = ScrapingLogORM(
                    source=stats["source"],
                    started_at=result.started_at,
                    finished_at=result.finished_at or datetime.utcnow(),
                    duration_seconds=result.duration_seconds,
                    jobs_found=stats.get("found", 0),
                    jobs_inserted=stats.get("inserted", 0),
                    jobs_duplicated=stats.get("duplicated", 0),
                    jobs_failed=stats.get("failed", 0),
                    errors=stats.get("errors", []),
                    status=stats.get("status", "SUCCESS"),
                )
                session.add(log)
                await session.commit()
        except Exception as e:
            logger.error(f"[Runner] Erro ao salvar scraping log: {e}")
