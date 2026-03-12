# ============================================================
# Normaliza RawJob de qualquer fonte → campos comuns limpos
# ============================================================
from __future__ import annotations
import re
from scraper.base_scraper import RawJob


class JobNormalizer:
    """
    Normaliza texto bruto de vagas de diferentes fontes.
    Garante que o LLM receba input limpo e consistente.
    """

    # Padrões para remoção de ruído
    _HTML_TAG = re.compile(r"<[^>]+>")
    _MULTI_SPACE = re.compile(r"[ \t]{2,}")
    _MULTI_NEWLINE = re.compile(r"\n{3,}")
    _BULLET_VARIANTS = re.compile(r"^[\s]*[•·▪▸➤➔◆\-–—*]+\s*", re.MULTILINE)

    # Limite de caracteres do texto bruto enviado ao LLM
    MAX_TEXT_LENGTH = 8000

    def normalize(self, job: RawJob) -> RawJob:
        """Limpa e padroniza os campos de um RawJob."""
        job.title = self._clean_text(job.title)
        job.company = self._clean_text(job.company)
        job.raw_text = self._clean_body(job.raw_text)
        if job.location:
            job.location = self._clean_text(job.location)
        return job

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = self._HTML_TAG.sub(" ", text)
        text = self._MULTI_SPACE.sub(" ", text)
        return text.strip()

    def _clean_body(self, text: str) -> str:
        if not text:
            return ""
        text = self._HTML_TAG.sub("\n", text)           # HTML → quebras de linha
        text = self._BULLET_VARIANTS.sub("- ", text)    # padroniza bullets
        text = self._MULTI_SPACE.sub(" ", text)
        text = self._MULTI_NEWLINE.sub("\n\n", text)
        text = text.strip()
        # Trunca para não explodir o contexto do LLM
        if len(text) > self.MAX_TEXT_LENGTH:
            text = text[:self.MAX_TEXT_LENGTH] + "\n\n[texto truncado]"
        return text

    def build_llm_input(self, job: RawJob) -> str:
        """
        Monta o texto final que será enviado ao Llama 3 para extração estruturada.
        Formato padronizado entre todas as fontes.
        """
        return (
            f"TÍTULO DA VAGA: {job.title}\n"
            f"EMPRESA: {job.company}\n"
            f"LOCALIZAÇÃO: {job.location or 'Não informado'}\n"
            f"FONTE: {job.source}\n\n"
            f"DESCRIÇÃO COMPLETA:\n{job.raw_text}"
        )
