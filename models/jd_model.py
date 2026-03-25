from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from models.cv_model import Language
from models.verdict import JobDomain, LanguageProficiency, SeniorityLevel, SkillLevel


class RequiredSkill(BaseModel):
    name: str
    level: SkillLevel = SkillLevel.NAO_INFORMADO
    is_required: bool = True          # False = desejável / nice-to-have
    aliases: list[str] = Field(default_factory=list)
    weight: float = 1.0               # peso no scoring (0.0 – 1.0)

    # ── Contrato de confiança ─────────────────────────────────────────────
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # "explicit_required"  → texto usa "obrigatório", "requisito", "required"
    # "explicit_desired"   → texto usa "desejável", "diferencial", "nice to have"
    # "inferred_required"  → LLM inferiu obrigatoriedade sem marcação explícita
    # "inferred_desired"   → LLM inferiu como desejável
    classification_source: str = "explicit_required"


class JobDescription(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    # Dados da vaga
    title: str
    company: str = ""
    description_raw: str = ""
    responsibilities: list[str] = Field(default_factory=list)

    # Classificação
    domain: JobDomain = JobDomain.OTHER
    seniority: SeniorityLevel = SeniorityLevel.NAO_INFORMADO

    # Requisitos técnicos
    required_skills: list[RequiredSkill] = Field(default_factory=list)

    # Experiência
    min_experience_years: float = 0.0
    max_experience_years: Optional[float] = None

    # Formação
    education_requirements: list[str] = Field(default_factory=list)
    certifications_required: list[str] = Field(default_factory=list)

    # Idiomas
    languages_required: list[Language] = Field(default_factory=list)

    # Soft skills
    soft_skills_mentioned: list[str] = Field(default_factory=list)

    # Metadados de scraping
    source: str = "manual"
    source_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True

    # ── Contrato de confiança por campo ───────────────────────────────────
    skills_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Média das confidences das required_skills

    experience_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # 1.0 se min_experience_years veio de texto explícito ("mínimo 3 anos")
    # 0.7 se inferido de senioridade
    # 0.4 se não mencionado
    experience_source: str = "not_informed"
    # "explicit"  → "mínimo X anos", "X+ anos de experiência"
    # "inferred"  → derivado da senioridade ou contexto
    # "not_informed"

    seniority_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    seniority_source: str = "not_informed"
    # "explicit_title"   → vaga traz "Desenvolvedor Sênior" no título
    # "explicit_body"    → corpo da vaga menciona senioridade
    # "inferred_years"   → derivado de min_experience_years
    # "not_informed"

    # Confiança global (mantida para compatibilidade)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_warnings: list[str] = Field(default_factory=list)

    # ── Validator ─────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def compute_derived_fields(self) -> "JobDescription":
        self._recalc_skills_confidence()
        self._recalc_overall_confidence()
        return self

    def _recalc_skills_confidence(self):
        if not self.required_skills:
            self.skills_confidence = 0.0
            return
        self.skills_confidence = round(
            sum(s.confidence for s in self.required_skills) / len(self.required_skills), 3
        )

    def _recalc_overall_confidence(self):
        """Confiança global ponderada pelos campos críticos da JD."""
        seniority_ok = 1.0 if self.seniority != SeniorityLevel.NAO_INFORMADO else 0.5
        self.extraction_confidence = round(
            self.skills_confidence     * 0.50 +
            self.experience_confidence * 0.25 +
            seniority_ok               * 0.15 +
            self.seniority_confidence  * 0.10,
            3,
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def get_required_skill_names(self) -> set[str]:
        names = set()
        for s in self.required_skills:
            if s.is_required:
                names.add(s.name.lower())
                names.update(a.lower() for a in s.aliases)
        return names

    def get_desired_skill_names(self) -> set[str]:
        names = set()
        for s in self.required_skills:
            if not s.is_required:
                names.add(s.name.lower())
                names.update(a.lower() for a in s.aliases)
        return names

    def get_reliable_required_skills(self, min_confidence: float = 0.7) -> list[RequiredSkill]:
        """Retorna skills obrigatórias com confiança suficiente para serem bloqueadores."""
        return [
            s for s in self.required_skills
            if s.is_required and s.confidence >= min_confidence
        ]

    def has_low_confidence_warning(self) -> bool:
        return (
            self.skills_confidence     < 0.6
            or self.experience_confidence < 0.5
        )
