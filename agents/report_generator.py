# ============================================================
# LLM redige o parecer com base nos números já calculados.
# Esta é a ÚNICA parte da Fase 3 que usa o LLM.
# ============================================================
from __future__ import annotations
import json
import re
from typing import Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from config.prompts.report import REPORT_SYSTEM, REPORT_PROMPT
from models.conformity_result import ConformityResult


class ReportGenerator:

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=settings.ollama_timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def generate(self, result: ConformityResult) -> ConformityResult:
        """
        Recebe um ConformityResult já com score/veredito calculados
        e adiciona os pareceres PT e EN gerados pelo LLM.
        """
        prompt = self._build_prompt(result)
        raw    = await self._call_llm(prompt)

        if not raw:
            result.parecer_final_pt = self._fallback_pt(result)
            result.parecer_final_en = self._fallback_en(result)
            return result

        parsed = self._parse_response(raw)
        result.parecer_final_pt = parsed.get("parecer_pt") or self._fallback_pt(result)
        result.parecer_final_en = parsed.get("parecer_en") or self._fallback_en(result)
        return result

    def _build_prompt(self, r: ConformityResult) -> str:
        dims = r.dimensions
        blocker_tag = "⚠️ BLOQUEADOR ATIVO" if r.has_absolute_blocker else ""
        return REPORT_PROMPT.format(
            candidate_name=r.candidate_name,
            jd_title=r.jd_title,
            verdict=r.verdict.value,
            score=r.overall_score,
            skills_score=dims.hard_skills.score if dims else "N/A",
            skills_blocker=blocker_tag,
            exp_score=dims.experience.score if dims else "N/A",
            edu_score=dims.education.score if dims else "N/A",
            lang_score=dims.languages.score if dims else "N/A",
            strengths="\n".join(f"- {s}" for s in r.strengths) or "Nenhum identificado",
            gaps="\n".join(f"- {g}" for g in r.critical_gaps) or "Nenhuma lacuna crítica",
            partial="\n".join(f"- {p}" for p in r.partial_matches) or "Nenhum",
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=6),
        reraise=False,
    )
    async def _call_llm(self, prompt: str) -> Optional[str]:
        try:
            resp = await self._client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "options": {
                        "temperature": 0.4,   # um pouco mais criativo para linguagem natural
                        "num_predict": 1024,
                        "num_ctx": 4096,
                    },
                    "messages": [
                        {"role": "system", "content": REPORT_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            logger.error(f"[ReportGenerator] Erro ao chamar LLM: {e}")
            return None

    def _parse_response(self, raw: str) -> dict:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        match   = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}

    # Pareceres de fallback — gerados sem LLM se ele falhar
    def _fallback_pt(self, r: ConformityResult) -> str:
        return (
            f"Candidato: {r.candidate_name} | Vaga: {r.jd_title}\n"
            f"Veredito: {r.verdict.value} | Score: {r.overall_score}/100\n"
            f"Lacunas: {', '.join(r.critical_gaps) or 'nenhuma'} | "
            f"Pontos fortes: {', '.join(r.strengths[:3]) or 'não identificados'}"
        )

    def _fallback_en(self, r: ConformityResult) -> str:
        return (
            f"Candidate: {r.candidate_name} | Position: {r.jd_title}\n"
            f"Verdict: {r.verdict.value} | Score: {r.overall_score}/100\n"
            f"Gaps: {', '.join(r.critical_gaps) or 'none'} | "
            f"Strengths: {', '.join(r.strengths[:3]) or 'not identified'}"
        )
