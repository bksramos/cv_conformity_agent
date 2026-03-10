from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date
from uuid import UUID, uuid4
from models.verdict import SeniorityLevel, SkillLevel, LanguageProficiency


class Skill(BaseModel):
    name: str
    level: SkillLevel = SkillLevel.NAO_INFORMADO
    years_of_use: Optional[float] = None
    # True se a skill aparece na descrição de alguma experiência
    # (valida que não é só um "keyword dump" no CV)
    mentioned_in_experience: bool = False
    aliases: list[str] = Field(default_factory=list)  # ex: ["JS", "JavaScript"]


class Language(BaseModel):
    name: str                                        # "Inglês", "Espanhol"
    proficiency: LanguageProficiency = LanguageProficiency.BASICO
    certified: bool = False                          # TOEFL, IELTS, etc.


class Education(BaseModel):
    degree: str                                      # "Bacharelado", "MBA", "Pós"
    field_of_study: str                              # "Ciência da Computação"
    institution: str
    graduation_year: Optional[int] = None
    is_complete: bool = True


class WorkExperience(BaseModel):
    company: str
    role: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None                  # None = emprego atual
    duration_months: Optional[int] = None            # calculado automaticamente
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    domain: Optional[str] = None                     # fintech, healthtech, varejo


    @field_validator("duration_months", mode="before")
    @classmethod
    def calc_duration(cls, v, info):
        if v is not None:
            return v
        data = info.data
        start = data.get("start_date")
        end = data.get("end_date") or date.today()
        if start:
            delta = (end.year - start.year) * 12 + (end.month - start.month)
            return max(delta, 0)
        return None


class CVProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pdf_hash: str = ""                               # SHA256 do PDF original

    # Dados pessoais
    candidate_name: str = "Desconhecido"
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None

    # Sumário / objetivo
    summary: Optional[str] = None

    # Competências
    hard_skills: list[Skill] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)

    # Experiência
    experiences: list[WorkExperience] = Field(default_factory=list)
    total_experience_years: float = 0.0              # calculado somando durations
    seniority_inferred: SeniorityLevel = SeniorityLevel.NAO_INFORMADO

    # Formação e idiomas
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)

    # Metadados de extração
    extraction_confidence: float = 0.0              # 0.0 - 1.0
    extraction_strategy: str = "pymupdf"            # "pymupdf" | "pdfplumber" | "llm"
    extraction_warnings: list[str] = Field(default_factory=list)

    def calc_total_experience(self) -> float:
        """Soma todos os períodos de experiência em anos."""
        total_months = sum(
            e.duration_months for e in self.experiences
            if e.duration_months is not None
        )
        self.total_experience_years = round(total_months / 12, 1)
        return self.total_experience_years

    def get_skill_names(self) -> set[str]:
        names = {s.name.lower() for s in self.hard_skills}
        for s in self.hard_skills:
            names.update(a.lower() for a in s.aliases)
        return names

