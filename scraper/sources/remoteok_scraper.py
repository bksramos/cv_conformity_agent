# ============================================================
# Remote OK — JSON API pública, foco em vagas tech remotas
# Docs: https://remoteok.com/api
# ============================================================
from __future__ import annotations
from datetime import datetime
from typing import Optional

import httpx
from loguru import logger

from scraper.base_scraper import BaseScraper, RawJob, ScraperResult

# Tags de interesse para filtrar apenas vagas relevantes
RELEVANT_TAGS = {
    "python", "javascript", "typescript", "node", "react", "vue", "angular",
    "java", "golang", "rust", "ruby", "php", "swift", "kotlin",
    "backend", "frontend", "fullstack", "devops", "cloud", "aws", "gcp", "azure",
    "data", "machine-learning", "ai", "ml", "data-science", "analytics",
    "engineer", "developer", "software", "api", "docker", "kubernetes",
}


class RemoteOKScraper(BaseScraper):
    name = "remoteok"

    API_URL = "https://remoteok.com/api"
    MAX_JOBS = 150    # API retorna tudo de uma vez, limitamos aqui

    async def fetch_jobs(self) -> ScraperResult:
        self._log_start()
        result = ScraperResult(source=self.name)

        try:
            # RemoteOK exige User-Agent específico (não bloqueia bots declarados)
            resp = await self._get(
                self.API_URL,
                headers={"Accept": "application/json"}
            )
            data = resp.json()

            # Primeiro item é sempre metadata da API, pular
            items = [i for i in data if isinstance(i, dict) and i.get("id")]

            count = 0
            for item in items:
                if count >= self.MAX_JOBS:
                    break
                job = self._parse_item(item)
                if job:
                    result.jobs.append(job)
                    count += 1

            logger.info(f"[remoteok] {len(result.jobs)} vagas relevantes de {len(items)} recebidas")

        except httpx.HTTPStatusError as e:
            msg = f"[remoteok] HTTP {e.response.status_code}"
            logger.error(msg)
            result.errors.append(msg)
        except Exception as e:
            msg = f"[remoteok] Erro: {type(e).__name__}: {e}"
            logger.error(msg)
            result.errors.append(msg)

        result.finish()
        self._log_finish(result)
        return result

    def _is_relevant(self, item: dict) -> bool:
        """Filtra vagas por tags de interesse."""
        tags = {t.lower() for t in (item.get("tags") or [])}
        return bool(tags & RELEVANT_TAGS)

    def _parse_item(self, item: dict) -> Optional[RawJob]:
        try:
            if not self._is_relevant(item):
                return None

            job_id = item.get("id", "")
            title = item.get("position", "").strip()
            company = item.get("company", "").strip()
            source_url = item.get("url") or f"https://remoteok.com/remote-jobs/{job_id}"

            # Monta texto bruto a partir dos campos disponíveis
            description = item.get("description") or ""
            tags_text = "Tags: " + ", ".join(item.get("tags") or [])
            salary = item.get("salary") or ""
            salary_text = f"Faixa salarial: {salary}" if salary else ""

            raw_text = "\n\n".join(filter(None, [description, tags_text, salary_text]))

            if not title or not raw_text:
                return None

            # Data de publicação
            epoch = item.get("epoch")
            scraped_at = datetime.fromtimestamp(epoch) if epoch else datetime.utcnow()

            return RawJob(
                source=self.name,
                source_url=source_url,
                title=title,
                company=company,
                raw_text=raw_text,
                location="Remote",
                scraped_at=scraped_at,
                extra={
                    "job_id": job_id,
                    "tags": item.get("tags", []),
                    "salary": salary,
                    "apply_url": item.get("apply_url"),
                },
            )
        except Exception as e:
            logger.warning(f"[remoteok] Erro ao parsear item {item.get('id')}: {e}")
            return None