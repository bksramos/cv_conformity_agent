# ============================================================
# Extrai JobDescription estruturada de texto bruto via Llama 3
# ============================================================
from __future__ import annotations
import json
import re
from typing import Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from config.prompts.jd_extraction import JD_EXTRACTION_SYSTEM, JD_EXTRACTION_PROMPT
from models.jd_model import JobDescription, RequiredSkill
from models.cv_model import Language
from models.verdict import JobDomain, SeniorityLevel, SkillLevel, LanguageProficiency
from scraper.base_scraper import RawJob
from scraper.normalizer import JobNormalizer


class JDExtractionAgent:
    """
    Agent responsável por converter RawJob → JobDescription estruturada.
    Usa Llama 3 via Ollama para extração semântica.
    Análogo ao vt_extraction_agent do Feito/Conferido.
    """

    def __init__(self):
        self._normalizer = JobNormalizer()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=settings.ollama_timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def extract(self, raw_job: RawJob) -> Optional[JobDescription]:
        """
        Pipeline completo: normaliza → monta prompt → chama LLM → parseia → valida.
        Retorna None se a extração falhar completamente.
        """
        # 1. Normaliza texto bruto
        normalized = self._normalizer.normalize(raw_job)
        llm_input = self._normalizer.build_llm_input(normalized)

        # 2. Chama Llama 3
        raw_response = await self._call_llm(llm_input)
        if not raw_response:
            logger.error(f"[JDExtraction] LLM não retornou resposta para: {raw_job.title}")
            return None

        # 3. Parseia JSON da resposta
        parsed = self._parse_llm_response(raw_response, raw_job.title)
        if not parsed:
            return None

        # 4. Converte dict → JobDescription
        jd = self._build_jd(parsed, raw_job)
        logger.info(
            f"[JDExtraction] ✅ '{jd.title}' | "
            f"domínio={jd.domain.value} | sênior={jd.seniority.value} | "
            f"skills={len(jd.required_skills)} | conf={jd.extraction_confidence:.2f}"
        )
        return jd

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=False,
    )
    async def _call_llm(self, job_text: str) -> Optional[str]:
        """Chama Ollama com o prompt de extração."""
        prompt = JD_EXTRACTION_PROMPT.format(job_text=job_text)
        try:
            resp = await self._client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1024,
                        "num_ctx": 4096,
                        "num_gpu": 999,   # usa todas as camadas disponíveis na GPU
                        "num_thread": 8,  # threads CPU para as camadas que não cabem na VRAM
                    },
                    "messages": [
                        {"role": "system", "content": JD_EXTRACTION_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except httpx.TimeoutException:
            logger.warning("[JDExtraction] Timeout no LLM — tentando novamente...")
            raise
        except Exception as e:
            logger.error(f"[JDExtraction] Erro ao chamar LLM: {e}")
            return None

    def _parse_llm_response(self, raw: str, title: str) -> Optional[dict]:
        """
        Parseia a resposta do LLM extraindo o JSON.
        Lida com casos onde o LLM adiciona markdown ou texto extra.
        """
        # Remove blocos de código markdown se existirem
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()

        # Tenta encontrar o JSON dentro da resposta
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            logger.warning(f"[JDExtraction] JSON não encontrado na resposta para: {title}")
            logger.debug(f"[JDExtraction] Resposta bruta: {raw[:300]}")
            return None

        try:
            return json.loads(match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"[JDExtraction] JSON inválido para '{title}': {e}")
            return None

    def _build_jd(self, data: dict, raw_job: RawJob) -> JobDescription:
        """Converte o dict extraído pelo LLM → JobDescription Pydantic."""

        # --- Enums com fallback seguro ---
        def safe_domain(v) -> JobDomain:
            try:
                return JobDomain(v.upper()) if v else JobDomain.OTHER
            except ValueError:
                return JobDomain.OTHER

        def safe_seniority(v) -> SeniorityLevel:
            try:
                return SeniorityLevel(v.upper()) if v else SeniorityLevel.NAO_INFORMADO
            except ValueError:
                return SeniorityLevel.NAO_INFORMADO

        def safe_skill_level(v) -> SkillLevel:
            try:
                return SkillLevel(v.upper()) if v else SkillLevel.NAO_INFORMADO
            except ValueError:
                return SkillLevel.NAO_INFORMADO

        def safe_proficiency(v) -> LanguageProficiency:
            try:
                return LanguageProficiency(v.upper()) if v else LanguageProficiency.BASICO
            except ValueError:
                return LanguageProficiency.BASICO

        # --- Skills ---
        skills = []
        for s in (data.get("required_skills") or []):
            if not s.get("name"):
                continue
            skills.append(RequiredSkill(
                name=s["name"].strip(),
                level=safe_skill_level(s.get("level")),
                is_required=bool(s.get("is_required", True)),
                aliases=[a.strip() for a in (s.get("aliases") or []) if a],
            ))

        # --- Idiomas ---
        languages = []
        for lang in (data.get("languages_required") or []):
            if not lang.get("name"):
                continue
            languages.append(Language(
                name=lang["name"].strip(),
                proficiency=safe_proficiency(lang.get("proficiency")),
            ))

        return JobDescription(
            title=data.get("title") or raw_job.title,
            company=data.get("company") or raw_job.company,
            description_raw=raw_job.raw_text,
            domain=safe_domain(data.get("domain")),
            seniority=safe_seniority(data.get("seniority")),
            min_experience_years=float(data.get("min_experience_years") or 0),
            max_experience_years=(
                float(data["max_experience_years"])
                if data.get("max_experience_years") is not None else None
            ),
            required_skills=skills,
            education_requirements=data.get("education_requirements") or [],
            certifications_required=data.get("certifications_required") or [],
            languages_required=languages,
            soft_skills_mentioned=data.get("soft_skills_mentioned") or [],
            responsibilities=data.get("responsibilities") or [],
            source=raw_job.source,
            source_url=raw_job.source_url,
            scraped_at=raw_job.scraped_at,
            extraction_confidence=float(data.get("extraction_confidence") or 0.5),
        )