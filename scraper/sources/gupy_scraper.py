# ============================================================
# Gupy — API REST pública, foco em vagas tech brasileiras
# Docs: https://portal.api.gupy.io/api/v1/jobs
# ============================================================
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from loguru import logger

from scraper.base_scraper import BaseScraper, RawJob, ScraperResult


class GupyScraper(BaseScraper):
    name = "gupy"

    BASE_URL = "https://portal.api.gupy.io/api/v1/jobs"

    # Filtros de busca — focado em tech para a Fase 1
    SEARCH_QUERIES = [
        "engenheiro de software",
        "desenvolvedor backend",
        "desenvolvedor frontend",
        "desenvolvedor fullstack",
        "engenheiro de dados",
        "data scientist",
        "machine learning",
        "devops",
        "cloud engineer",
        "arquiteto de software",
    ]

    PAGE_SIZE = 20    # máximo permitido pela API
    MAX_PAGES = 5     # até 100 vagas por query

    async def fetch_jobs(self) -> ScraperResult:
        self._log_start()
        result = ScraperResult(source=self.name)

        # Semaphore para limitar concorrência entre queries
        sem = asyncio.Semaphore(3)

        async def fetch_query(query: str):
            async with sem:
                jobs = await self._fetch_query(query, result)
                return jobs

        tasks = [fetch_query(q) for q in self.SEARCH_QUERIES]
        await asyncio.gather(*tasks, return_exceptions=True)

        result.finish()
        self._log_finish(result)
        return result

    async def _fetch_query(self, query: str, result: ScraperResult) -> list[RawJob]:
        jobs = []
        for page in range(1, self.MAX_PAGES + 1):
            try:
                page_jobs = await self._fetch_page(query, page)
                if not page_jobs:
                    break                       # sem mais resultados
                jobs.extend(page_jobs)
                result.jobs.extend(page_jobs)
                logger.debug(f"[gupy] '{query}' — página {page}: {len(page_jobs)} vagas")
            except httpx.HTTPStatusError as e:
                msg = f"[gupy] HTTP {e.response.status_code} em '{query}' p{page}"
                logger.warning(msg)
                result.errors.append(msg)
                break
            except Exception as e:
                msg = f"[gupy] Erro em '{query}' p{page}: {type(e).__name__}: {e}"
                logger.error(msg)
                result.errors.append(msg)
                break
        return jobs

    async def _fetch_page(self, query: str, page: int) -> list[RawJob]:
        params = {
            "jobName": query,
            "limit": self.PAGE_SIZE,
            "offset": (page - 1) * self.PAGE_SIZE,
        }
        resp = await self._get(self.BASE_URL, params=params)
        data = resp.json()

        raw_jobs = data.get("data", [])
        if not raw_jobs:
            return []

        jobs = []
        for item in raw_jobs:
            job = self._parse_item(item)
            if job:
                jobs.append(job)
        return jobs

    def _parse_item(self, item: dict) -> Optional[RawJob]:
        try:
            job_id = item.get("id")
            title = item.get("name", "").strip()
            company = item.get("company", {}).get("name", "") if isinstance(item.get("company"), dict) else ""
            # A API da Gupy retorna bool em city/state quando não informado
            city = item.get("city") or ""
            state = item.get("state") or ""
            city = city if isinstance(city, str) else ""
            state = state if isinstance(state, str) else ""
            parts = [p for p in [city, state] if p.strip()]
            location = ", ".join(parts) if parts else None

            # Monta URL canônica da vaga
            company_slug = item.get("company", {}).get("name", "").lower().replace(" ", "-") \
                if isinstance(item.get("company"), dict) else "empresa"
            source_url = f"https://portal.gupy.io/job/{job_id}"

            # Gupy pode retornar bool em campos de texto — força str em tudo
            def safe_str(v) -> str:
                if isinstance(v, str):
                    return v.strip()
                return ""

            description = safe_str(item.get("description"))
            prerequisites = safe_str(item.get("prerequisites"))
            disabilities = safe_str(item.get("disabilities"))

            raw_text = "\n\n".join(p for p in [description, prerequisites, disabilities] if p)

            if not title or not raw_text:
                return None

            return RawJob(
                source=self.name,
                source_url=source_url,
                title=title,
                company=company,
                raw_text=raw_text,
                location=location,
                scraped_at=datetime.utcnow(),
                extra={
                    "job_id": job_id,
                    "type": item.get("type"),
                    "workplace_type": item.get("workplaceType"),
                    "published_at": item.get("publishedDate"),
                },
            )
        except Exception as e:
            logger.warning(f"[gupy] Erro ao parsear item {item.get('id')}: {e}")
            return None

