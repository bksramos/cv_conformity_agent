# ============================================================
# Classe abstrata — todos os scrapers herdam daqui
# ============================================================
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import asyncio
import random

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings


@dataclass
class RawJob:
    """
    Estrutura intermediária — saída bruta de qualquer scraper,
    antes da normalização e extração pelo LLM.
    """
    source: str
    source_url: str
    title: str
    company: str
    raw_text: str                          # descrição completa da vaga
    location: Optional[str] = None
    salary: Optional[str] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    extra: dict = field(default_factory=dict)  # campos específicos por fonte


@dataclass
class ScraperResult:
    """Resultado de uma execução completa do scraper."""
    source: str
    jobs: list[RawJob] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    @property
    def total_found(self) -> int:
        return len(self.jobs)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def finish(self):
        self.finished_at = datetime.utcnow()


class BaseScraper(ABC):
    """
    Classe base para todos os scrapers de vagas.
    Fornece: cliente HTTP compartilhado, retry, rate limiting e logging.
    """

    name: str = "base"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": "CVConformityAgent/1.0 (research bot)"},
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @abstractmethod
    async def fetch_jobs(self) -> ScraperResult:
        """
        Implementação específica por fonte.
        Deve retornar um ScraperResult com lista de RawJob.
        """
        ...

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """GET com retry automático e rate limiting."""
        await self._random_delay()
        logger.debug(f"[{self.name}] GET {url}")
        resp = await self._client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    async def _random_delay(self):
        """Delay aleatório entre requests para não sobrecarregar as fontes."""
        delay = random.uniform(settings.scraper_delay_min, settings.scraper_delay_max)
        await asyncio.sleep(delay)

    def _log_start(self):
        logger.info(f"[{self.name}] ▶ Iniciando scraping...")

    def _log_finish(self, result: ScraperResult):
        logger.info(
            f"[{self.name}] ✅ Finalizado em {result.duration_seconds:.1f}s — "
            f"{result.total_found} vagas encontradas, {len(result.errors)} erros"
        )
