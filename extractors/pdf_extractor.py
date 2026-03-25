# ============================================================
# Extrai texto bruto de PDFs — PyMuPDF (primário) + pdfplumber (fallback)
# ============================================================
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz                  # PyMuPDF
import pdfplumber
from loguru import logger


@dataclass
class RawCVText:
    """Texto bruto extraído do PDF antes de qualquer processamento semântico."""
    text: str
    pdf_hash: str            # SHA256 do arquivo — usado para cache
    num_pages: int
    strategy: str            # "pymupdf" | "pdfplumber"
    warnings: list[str]


class PDFExtractor:
    """
    Extrai texto de PDFs de currículos.
    Estratégia hierárquica:
      1. PyMuPDF  — rápido, preciso para a maioria dos PDFs
      2. pdfplumber — melhor para PDFs com tabelas e layouts complexos
    """

    MIN_TEXT_LENGTH = 200    # menos que isso indica PDF corrompido ou só imagem

    def extract(self, pdf_bytes: bytes) -> RawCVText:
        """Extrai texto do PDF em bytes."""
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        warnings = []

        # --- Estratégia 1: PyMuPDF ---
        try:
            text, pages = self._extract_pymupdf(pdf_bytes)
            if len(text.strip()) >= self.MIN_TEXT_LENGTH:
                logger.debug(f"[PDFExtractor] PyMuPDF OK — {pages} páginas, {len(text)} chars")
                return RawCVText(
                    text=text,
                    pdf_hash=pdf_hash,
                    num_pages=pages,
                    strategy="pymupdf",
                    warnings=warnings,
                )
            warnings.append(f"PyMuPDF retornou texto insuficiente ({len(text.strip())} chars)")
            logger.warning(f"[PDFExtractor] PyMuPDF insuficiente — tentando pdfplumber")
        except Exception as e:
            warnings.append(f"PyMuPDF falhou: {e}")
            logger.warning(f"[PDFExtractor] PyMuPDF erro: {e}")

        # --- Estratégia 2: pdfplumber ---
        try:
            text, pages = self._extract_pdfplumber(pdf_bytes)
            if len(text.strip()) >= self.MIN_TEXT_LENGTH:
                logger.debug(f"[PDFExtractor] pdfplumber OK — {pages} páginas, {len(text)} chars")
                return RawCVText(
                    text=text,
                    pdf_hash=pdf_hash,
                    num_pages=pages,
                    strategy="pdfplumber",
                    warnings=warnings,
                )
            warnings.append(f"pdfplumber retornou texto insuficiente ({len(text.strip())} chars)")
        except Exception as e:
            warnings.append(f"pdfplumber falhou: {e}")
            logger.warning(f"[PDFExtractor] pdfplumber erro: {e}")

        # --- Fallback: retorna o que tiver (LLM vai tentar extrair mesmo assim) ---
        logger.error(f"[PDFExtractor] Ambas estratégias falharam — PDF pode ser imagem")
        return RawCVText(
            text=text if "text" in dir() else "",
            pdf_hash=pdf_hash,
            num_pages=0,
            strategy="failed",
            warnings=warnings,
        )

    def extract_from_path(self, path: Path) -> RawCVText:
        return self.extract(path.read_bytes())

    def _extract_pymupdf(self, pdf_bytes: bytes) -> tuple[str, int]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text("text"))
        doc.close()
        return "\n\n".join(pages_text), len(pages_text)

    def _extract_pdfplumber(self, pdf_bytes: bytes) -> tuple[str, int]:
        import io
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                # Tenta extrair tabelas também (skills em formato tabular)
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        row_text = " | ".join(cell or "" for cell in row if cell)
                        if row_text.strip():
                            text += "\n" + row_text
                pages_text.append(text)
        return "\n\n".join(pages_text), len(pages_text)
