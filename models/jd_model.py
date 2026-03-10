from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4
from models.verdict import SeniorityLevel, JobDomain, SkillLevel, LanguageProficiency
from models.cv_model import Skill, Language


class RequiredSkill(BaseModel):
    """Skill da JD com flag de obrigatoriedade."""
    name: str
    level: SkillLevel = SkillLevel.NAO_INFORMADO
    is_required: bool = True                         # False = desejável
    aliases: list[str] = Field(default_factory=list)
    weight: float = 1.0                              # peso no scoring (0.0 - 1.0)


class JobDescription(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    # Dados da vaga
    title: str
    company: str = ""
    description_raw: str = ""                        # texto bruto da vaga
    responsibilities: list[str] = Field(default_factory=list)

    # Classificação
    domain: JobDomain = JobDomain.OTHER
    seniority: SeniorityLevel = SeniorityLevel.NAO_INFORMADO

    # Requisitos técnicos
    required_skills: list[RequiredSkill] = Field(default_factory=list)

    # Experiência
    min_experience_years: float = 0.0
    max_experience_years: Optional[float] = None     # teto (ex: "até 5 anos")

    # Formação
    education_requirements: list[str] = Field(default_factory=list)
    certifications_required: list[str] = Field(default_factory=list)

    # Idiomas
    languages_required: list[Language] = Field(default_factory=list)

    # Soft skills mencionadas
    soft_skills_mentioned: list[str] = Field(default_factory=list)

    # Metadados de scraping
    source: str = "manual"                           # "gupy" | "remoteok" | "manual"
    source_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True

    # Metadados de extração
    extraction_confidence: float = 0.0
    extraction_warnings: list[str] = Field(default_factory=list)

    def get_required_skill_names(self) -> set[str]:
        """Retorna nomes de skills OBRIGATÓRIAS em lowercase."""
        names = set()
        for s in self.required_skills:
            if s.is_required:
                names.add(s.name.lower())
                names.update(a.lower() for a in s.aliases)
        return names

    def get_desired_skill_names(self) -> set[str]:
        """Retorna nomes de skills DESEJÁVEIS em lowercase."""
        names = set()
        for s in self.required_skills:
            if not s.is_required:
                names.add(s.name.lower())
                names.update(a.lower() for a in s.aliases)
        return names

