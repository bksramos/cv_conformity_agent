from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4
from models.verdict import Verdict


class DimensionScore(BaseModel):
    """Score de uma dimensão individual — análogo ao DimensionScore do Feito/Conferido."""
    score: float                                     # 0.0 - 100.0
    weight: float                                    # peso desta dimensão no total
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    partial: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    is_blocked: bool = False                         # True = bloqueador absoluto ativo


class ConformityDimensions(BaseModel):
    hard_skills: DimensionScore
    experience: DimensionScore
    education: DimensionScore
    languages: DimensionScore
    soft_skills: DimensionScore


class ConformityResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    # Referências
    cv_hash: str                                     # SHA256 do PDF
    jd_id: UUID
    candidate_name: str = ""
    jd_title: str = ""

    # Veredito final
    verdict: Verdict = Verdict.PENDENTE
    overall_score: float = 0.0                       # 0-100 (ponderado)

    # Breakdown por dimensão
    dimensions: Optional[ConformityDimensions] = None

    # Destaques do parecer
    critical_gaps: list[str] = Field(default_factory=list)   # bloqueadores
    partial_matches: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)

    # Pareceres bilíngues gerados pelo Llama 3
    parecer_final_pt: str = ""
    parecer_final_en: str = ""

    # Metadados
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    llm_model_used: str = ""
    has_absolute_blocker: bool = False               # skill obrigatória ausente

    def set_verdict_from_score(self, threshold_approved: float, threshold_partial: float):
        """
        Define veredito com base no score.
        Análogo à lógica de verdict do core_validator do Feito/Conferido.
        Um bloqueador absoluto sobrescreve o score.
        """
        if self.has_absolute_blocker:
            self.verdict = Verdict.REPROVADO
            return

        if self.overall_score >= threshold_approved:
            self.verdict = Verdict.APROVADO
        elif self.overall_score >= threshold_partial:
            self.verdict = Verdict.APROVADO_COM_RESSALVAS
        else:
            self.verdict = Verdict.REPROVADO

