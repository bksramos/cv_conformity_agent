# ============================================================
# Limpa texto bruto extraído do PDF
# ============================================================
from __future__ import annotations
import re


class CVTextCleaner:
    """
    Limpa artefatos comuns de extração de PDF para CV.
    Prepara o texto para o LLM.
    """

    # Artefatos comuns de PDF
    _PAGE_NUMBERS    = re.compile(r"^\s*\d+\s*$", re.MULTILINE)
    _MULTI_NEWLINE   = re.compile(r"\n{3,}")
    _MULTI_SPACE     = re.compile(r"[ \t]{2,}")
    _BULLET_VARIANTS = re.compile(r"^[\s]*[•·▪▸➤➔◆■□▶→\-–—]+\s*", re.MULTILINE)
    _EMAIL_PATTERN   = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    _URL_PATTERN     = re.compile(r"https?://[^\s]+|linkedin\.com/in/[^\s]+|github\.com/[^\s]+")

    MAX_LENGTH = 12000   # limite para o contexto do Llama 3

    def clean(self, text: str) -> str:
        if not text:
            return ""

        text = self._PAGE_NUMBERS.sub("", text)
        text = self._BULLET_VARIANTS.sub("- ", text)
        text = self._MULTI_SPACE.sub(" ", text)
        text = self._MULTI_NEWLINE.sub("\n\n", text)
        text = self._fix_broken_lines(text)
        text = text.strip()

        if len(text) > self.MAX_LENGTH:
            text = text[:self.MAX_LENGTH] + "\n\n[texto truncado]"

        return text

    def _fix_broken_lines(self, text: str) -> str:
        """
        Junta linhas quebradas incorretamente pelo extrator do PDF.
        Ex: "Desenvolvedor\nSoftware" → "Desenvolvedor Software"
        Mantém quebras intencionais (parágrafos, seções).
        """
        lines = text.split("\n")
        fixed = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                fixed.append("")
                continue
            # Se a linha anterior não termina com pontuação e é curta,
            # provavelmente foi quebrada pelo extrator
            if (
                fixed
                and fixed[-1]
                and not fixed[-1].endswith((".", ":", ",", ";", "!", "?", "|", "-"))
                and len(fixed[-1]) < 60
                and not stripped[0].isupper()
            ):
                fixed[-1] = fixed[-1] + " " + stripped
            else:
                fixed.append(stripped)
        return "\n".join(fixed)

    def extract_contact_hints(self, text: str) -> dict:
        """
        Extrai email e URLs antes de limpar — salva hints para o LLM.
        """
        emails = self._EMAIL_PATTERN.findall(text)
        urls = self._URL_PATTERN.findall(text)
        return {
            "emails": list(set(emails)),
            "urls": list(set(urls)),
        }
