# ============================================================
# Rota dedicada à extração e análise do CVProfile
# ============================================================
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel
from typing import Optional

from agents.cv_extraction_agent import CVExtractionAgent
from config.settings import settings

router = APIRouter(tags=["CV"])


# ── Schemas de resposta ───────────────────────────────────────────────────────

class SkillOut(BaseModel):
    name: str
    level: str
    years_of_use: Optional[float]
    mentioned_in_experience: bool
    confidence: float
    source: str
    aliases: list[str]


class ExperienceOut(BaseModel):
    company: str
    role: str
    start_date: Optional[str]
    end_date: Optional[str]
    duration_months: Optional[int]
    duration_confidence: float
    duration_source: str
    description: str
    technologies: list[str]
    domain: Optional[str]


class EducationOut(BaseModel):
    degree: str
    field_of_study: str
    institution: str
    graduation_year: Optional[int]
    is_complete: bool


class LanguageOut(BaseModel):
    name: str
    proficiency: str
    certified: bool


class ExtractionContractOut(BaseModel):
    overall_confidence: float
    skills_confidence: float
    experience_confidence: float
    experience_source: str
    seniority_confidence: float
    seniority_source: str
    total_experience_years: float
    seniority_inferred: str
    has_low_confidence_warning: bool


class CVProfileOut(BaseModel):
    # Identificação
    candidate_name: str
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    linkedin_url: Optional[str]
    summary: Optional[str]

    # Competências
    hard_skills: list[SkillOut]
    soft_skills: list[str]

    # Experiência
    experiences: list[ExperienceOut]
    total_experience_years: float
    seniority_inferred: str

    # Formação e idiomas
    education: list[EducationOut]
    certifications: list[str]
    languages: list[LanguageOut]

    # Contrato de confiança
    contract: ExtractionContractOut

    # Metadados
    pdf_hash: str
    extraction_strategy: str
    extraction_warnings: list[str]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/cv/analyze",
    response_model=CVProfileOut,
    summary="Extrai e analisa um currículo PDF → CVProfile completo",
)
async def analyze_cv(
    pdf: UploadFile = File(..., description="PDF do currículo"),
):
    if pdf.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Arquivo deve ser um PDF")

    pdf_bytes = await pdf.read()
    logger.info(
        f"[cv/analyze] PDF recebido | arquivo='{pdf.filename}' size={len(pdf_bytes)} bytes"
    )

    async with CVExtractionAgent() as agent:
        profile = await agent.extract_from_bytes(pdf_bytes)

    if not profile or profile.candidate_name == "Desconhecido" and not profile.hard_skills:
        logger.error("[cv/analyze] Extração retornou perfil vazio")
        raise HTTPException(status_code=422, detail="Não foi possível extrair dados do PDF")

    def _fmt_date(d) -> Optional[str]:
        return d.strftime("%Y-%m") if d else None

    return CVProfileOut(
        candidate_name        = profile.candidate_name,
        email                 = profile.email,
        phone                 = profile.phone,
        location              = profile.location,
        linkedin_url          = profile.linkedin_url,
        summary               = profile.summary,
        hard_skills           = [
            SkillOut(
                name                    = s.name,
                level                   = s.level.value,
                years_of_use            = s.years_of_use,
                mentioned_in_experience = s.mentioned_in_experience,
                confidence              = s.confidence,
                source                  = s.source,
                aliases                 = s.aliases,
            )
            for s in profile.hard_skills
        ],
        soft_skills           = profile.soft_skills,
        experiences           = [
            ExperienceOut(
                company             = e.company,
                role                = e.role,
                start_date          = _fmt_date(e.start_date),
                end_date            = _fmt_date(e.end_date),
                duration_months     = e.duration_months,
                duration_confidence = e.duration_confidence,
                duration_source     = e.duration_source,
                description         = e.description,
                technologies        = e.technologies,
                domain              = e.domain,
            )
            for e in profile.experiences
        ],
        total_experience_years = profile.total_experience_years,
        seniority_inferred     = profile.seniority_inferred.value,
        education              = [
            EducationOut(
                degree          = e.degree,
                field_of_study  = e.field_of_study,
                institution     = e.institution,
                graduation_year = e.graduation_year,
                is_complete     = e.is_complete,
            )
            for e in profile.education
        ],
        certifications         = profile.certifications,
        languages              = [
            LanguageOut(
                name        = l.name,
                proficiency = l.proficiency.value,
                certified   = l.certified,
            )
            for l in profile.languages
        ],
        contract = ExtractionContractOut(
            overall_confidence          = profile.extraction_confidence,
            skills_confidence           = profile.skills_confidence,
            experience_confidence       = profile.experience_confidence,
            experience_source           = profile.experience_source,
            seniority_confidence        = profile.seniority_confidence,
            seniority_source            = profile.seniority_source,
            total_experience_years      = profile.total_experience_years,
            seniority_inferred          = profile.seniority_inferred.value,
            has_low_confidence_warning  = profile.has_low_confidence_warning(),
        ),
        pdf_hash               = profile.pdf_hash,
        extraction_strategy    = profile.extraction_strategy,
        extraction_warnings    = profile.extraction_warnings,
    )