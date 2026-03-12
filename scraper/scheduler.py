# ============================================================
# APScheduler — agenda o runner para rodar diariamente
# ============================================================
import asyncio
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config.settings import settings
from scraper.runner import ScraperRunner


class ScraperScheduler:
    """
    Agendador do pipeline de scraping.
    Roda diariamente no horário configurado via .env.
    """

    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
        self._runner = ScraperRunner()

    def start(self):
        trigger = CronTrigger(
            hour=settings.scraper_cron_hour,
            minute=settings.scraper_cron_minute,
        )
        self._scheduler.add_job(
            self._run_job,
            trigger=trigger,
            id="daily_scraping",
            name="Daily JD Scraping",
            replace_existing=True,
            misfire_grace_time=3600,  # tolera até 1h de atraso
        )
        self._scheduler.start()
        logger.info(
            f"[Scheduler] ✅ Scraping agendado para "
            f"{settings.scraper_cron_hour:02d}:{settings.scraper_cron_minute:02d} (Brasília)"
        )

    async def _run_job(self):
        logger.info("[Scheduler] ▶ Disparando ciclo de scraping agendado...")
        try:
            summary = await self._runner.run_all()
            logger.info(f"[Scheduler] ✅ Ciclo concluído: {summary}")
        except Exception as e:
            logger.error(f"[Scheduler] ❌ Erro no ciclo agendado: {e}")

    def stop(self):
        self._scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Scheduler parado.")
