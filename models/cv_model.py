from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from models.verdict import LanguageProficiency, SeniorityLevel, SkillLevel


# ─────────────────────────────────────────────────────────────────────────────
# Seniority calibration — regras determinísticas
# Usadas tanto pelo model_validator quanto pelo evaluate_quality
# ─────────────────────────────────────────────────────────────────────────────

SENIORITY_YEAR_RULES: list[tuple[float, float, SeniorityLevel]] = [
    (0.0,  0.5,  SeniorityLevel.ESTAGIO),
    (0.5,  2.0,  SeniorityLevel.JUNIOR),
    (2.0,  5.0,  SeniorityLevel.PLENO),
    (5.0,  9.0,  SeniorityLevel.SENIOR),
    (9.0,  14.0, SeniorityLevel.ESPECIALISTA),
    (14.0, 99.0, SeniorityLevel.LIDERANCA),
]

# Palavras no título que elevam ou confirmam senioridade
_TITLE_SENIOR_KEYWORDS   = {"senior", "sênior", "sr.", "sr ", "lead", "tech lead", "staff"}
_TITLE_LEAD_KEYWORDS     = {"gerente", "manager", "coordenador", "head", "diretor", "vp", "cto", "cio"}
_TITLE_JUNIOR_KEYWORDS   = {"junior", "júnior", "jr.", "jr ", "estágio", "estagiário", "trainee", "aprendiz"}
_TITLE_PLENO_KEYWORDS    = {"pleno", "pl.", "mid", "mid-level"}
_TITLE_SPEC_KEYWORDS     = {"especialista", "specialist", "architect", "arquiteto", "principal", "distinguished"}


def seniority_from_years(years: float) -> SeniorityLevel:
    """Retorna SeniorityLevel baseado apenas nos anos de experiência."""
    for low, high, level in SENIORITY_YEAR_RULES:
        if low <= years < high:
            return level
    return SeniorityLevel.NAO_INFORMADO


def calibrate_seniority(
    years: float,
    title_hints: list[str],
) -> tuple[SeniorityLevel, float, str]:
    """
    Deriva SeniorityLevel + confiança + fonte a partir de anos e títulos.

    Retorna: (seniority, confidence, source)
    - source: "years_only" | "title_only" | "cross_validated" | "title_overrides_years"
    """
    level_by_years = seniority_from_years(years)

    # Detecta keywords nos títulos (case-insensitive)
    combined = " ".join(t.lower() for t in title_hints)
    title_level: Optional[SeniorityLevel] = None
    if any(k in combined for k in _TITLE_LEAD_KEYWORDS):
        title_level = SeniorityLevel.LIDERANCA
    elif any(k in combined for k in _TITLE_SPEC_KEYWORDS):
        title_level = SeniorityLevel.ESPECIALISTA
    elif any(k in combined for k in _TITLE_SENIOR_KEYWORDS):
        title_level = SeniorityLevel.SENIOR
    elif any(k in combined for k in _TITLE_PLENO_KEYWORDS):
        title_level = SeniorityLevel.PLENO
    elif any(k in combined for k in _TITLE_JUNIOR_KEYWORDS):
        title_level = SeniorityLevel.JUNIOR

    if years == 0.0 and title_level is None:
        return SeniorityLevel.NAO_INFORMADO, 0.0, "no_data"

    if title_level is None:
        # Só anos disponíveis
        confidence = 0.70 if years > 0 else 0.30
        return level_by_years, confidence, "years_only"

    if years == 0.0:
        # Só título disponível
        return title_level, 0.55, "title_only"

    if title_level == level_by_years:
        # Anos e título concordam → alta confiança
        return level_by_years, 0.95, "cross_validated"

    # Discordância: título acima dos anos é comum (promoção recente, empresa pequena)
    # Título abaixo dos anos é raro e suspeito
    year_idx   = [l for _, _, l in SENIORITY_YEAR_RULES].index(level_by_years) if level_by_years in [l for _, _, l in SENIORITY_YEAR_RULES] else -1
    title_idx  = [l for _, _, l in SENIORITY_YEAR_RULES].index(title_level)    if title_level    in [l for _, _, l in SENIORITY_YEAR_RULES] else -1

    if title_idx > year_idx:
        # Título mais alto que anos: aceita título com confiança reduzida
        return title_level, 0.60, "title_overrides_years"
    else:
        # Título mais baixo que anos: anos provavelmente mais confiáveis
        return level_by_years, 0.65, "years_overrides_title"


# ─────────────────────────────────────────────────────────────────────────────
# Modelos
# ─────────────────────────────────────────────────────────────────────────────

class Skill(BaseModel):
    name: str
    level: SkillLevel = SkillLevel.NAO_INFORMADO
    years_of_use: Optional[float] = None
    mentioned_in_experience: bool = False
    aliases: list[str] = Field(default_factory=list)

    # ── Contrato de confiança ─────────────────────────────────────────────
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # "explicit"               → skill listada explicitamente na seção de skills
    # "inferred_from_exp"      → mencionada só nas experiências, não na seção skills
    # "inferred_from_context"  → inferida pelo LLM a partir de contexto
    source: str = "explicit"


class Language(BaseModel):
    name: str
    proficiency: LanguageProficiency = LanguageProficiency.BASICO
    certified: bool = False


class Education(BaseModel):
    degree: str
    field_of_study: str
    institution: str
    graduation_year: Optional[int] = None
    is_complete: bool = True


class WorkExperience(BaseModel):
    company: str
    role: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None       # None = emprego atual
    duration_months: Optional[int] = None
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    domain: Optional[str] = None

    # ── Contrato de confiança ─────────────────────────────────────────────
    duration_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # "calculated"  → calculado de start_date + end_date (mais confiável)
    # "stated"      → o próprio CV informa "2 anos" sem datas
    # "estimated"   → LLM estimou a partir de contexto parcial
    duration_source: str = "calculated"

    @field_validator("duration_months", mode="before")
    @classmethod
    def calc_duration(cls, v, info):
        if v is not None:
            return v
        data = info.data
        start = data.get("start_date")
        end   = data.get("end_date") or date.today()
        if start:
            delta = (end.year - start.year) * 12 + (end.month - start.month)
            return max(delta, 0)
        return None


class CVProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pdf_hash: str = ""

    # Dados pessoais
    candidate_name: str = "Desconhecido"
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None

    summary: Optional[str] = None

    # Competências
    hard_skills: list[Skill] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)

    # Experiência
    experiences: list[WorkExperience] = Field(default_factory=list)
    total_experience_years: float = 0.0
    seniority_inferred: SeniorityLevel = SeniorityLevel.NAO_INFORMADO

    # Formação e idiomas
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)

    # ── Contrato de confiança por campo ───────────────────────────────────
    seniority_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    seniority_source: str = "not_calculated"
    # "cross_validated"       → anos e títulos concordam       (≥ 0.90)
    # "years_only"            → calculado apenas por anos      (0.70)
    # "title_only"            → apenas título disponível       (0.55)
    # "title_overrides_years" → título mais alto que anos      (0.60)
    # "years_overrides_title" → anos mais altos que título     (0.65)
    # "no_data"               → sem dados suficientes          (0.00)

    experience_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Proporção de experiências com datas completas
    experience_source: str = "not_calculated"
    # "all_dated"    → todas as experiências têm start+end
    # "partial_dated"→ algumas experiências têm datas
    # "stated_only"  → duração declarada sem datas

    skills_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Média das confidences das hard_skills

    # Confiança global e avisos (mantidos para compatibilidade)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_strategy: str = "pymupdf"
    extraction_warnings: list[str] = Field(default_factory=list)

    # ── Validators ────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def compute_derived_fields(self) -> "CVProfile":
        self._recalc_experience()
        self._recalc_seniority()
        self._recalc_skills_confidence()
        self._recalc_overall_confidence()
        return self

    def _recalc_experience(self):
        """Recalcula total_experience_years e experience_confidence."""
        if not self.experiences:
            self.experience_confidence = 0.0
            self.experience_source     = "no_experiences"
            return

        # Preserva o valor fornecido pelo LLM antes de sobrescrever
        llm_total    = self.total_experience_years
        total_months = 0
        dated_count  = 0
        stated_count = 0

        for exp in self.experiences:
            if exp.start_date:
                end    = exp.end_date or date.today()
                # Contagem inclusiva: primeiro dia do mês inicial → último dia do mês final
                months = (end.year * 12 + end.month) - (exp.start_date.year * 12 + exp.start_date.month) + 1
                months = max(months, 1)
                exp.duration_months     = months
                exp.duration_confidence = 1.0
                exp.duration_source     = "calculated"
                total_months += months
                dated_count  += 1
            elif exp.duration_months:
                total_months += exp.duration_months
                exp.duration_source     = "stated"
                exp.duration_confidence = 0.70
                stated_count += 1

        calculated_total = round(total_months / 12, 1)
        total_exp        = len(self.experiences)

        if calculated_total > 0:
            self.total_experience_years = calculated_total
            if dated_count == total_exp:
                self.experience_confidence = 1.0
                self.experience_source     = "all_dated"
            elif dated_count > 0:
                self.experience_confidence = round(dated_count / total_exp, 2)
                self.experience_source     = "partial_dated"
            else:
                self.experience_confidence = 0.55
                self.experience_source     = "stated_only"
        elif llm_total > 0:
            self.total_experience_years = llm_total
            self.experience_confidence  = 0.45
            self.experience_source      = "llm_stated"
            self.extraction_warnings.append(
                f"Datas ausentes — usando total declarado pelo LLM: {llm_total} anos (confiança 0.45)"
            )
        else:
            self.total_experience_years = 0.0
            self.experience_confidence  = 0.0
            self.experience_source      = "no_data"
            self.extraction_warnings.append(
                "Não foi possível calcular total de experiência: sem datas e sem valor do LLM"
            )

    def _recalc_seniority(self):
        """Calibra senioridade usando anos + títulos, de forma determinística."""
        titles = [e.role for e in self.experiences if e.role]
        level, confidence, source = calibrate_seniority(
            self.total_experience_years, titles
        )
        # Só sobrescreve se o LLM retornou NAO_INFORMADO ou se calculamos com mais confiança
        if self.seniority_inferred == SeniorityLevel.NAO_INFORMADO or confidence > self.seniority_confidence:
            self.seniority_inferred   = level
            self.seniority_confidence = confidence
            self.seniority_source     = source

    def _recalc_skills_confidence(self):
        """Média das confidences das hard_skills."""
        if not self.hard_skills:
            self.skills_confidence = 0.0
            return
        self.skills_confidence = round(
            sum(s.confidence for s in self.hard_skills) / len(self.hard_skills), 3
        )

    def _recalc_overall_confidence(self):
        """
        Confiança global ponderada pelos campos mais críticos para o scoring.
        Pesos alinhados com os pesos do conformity_validator.
        """
        self.extraction_confidence = round(
            self.skills_confidence     * 0.40 +
            self.experience_confidence * 0.30 +
            (1.0 if self.education else 0.5) * 0.15 +
            (1.0 if self.languages else 0.8) * 0.10 +
            self.seniority_confidence  * 0.05,
            3,
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def get_skill_names(self) -> set[str]:
        names = {s.name.lower() for s in self.hard_skills}
        for s in self.hard_skills:
            names.update(a.lower() for a in s.aliases)
        return names

    def get_reliable_skills(self, min_confidence: float = 0.7) -> list[Skill]:
        """Retorna apenas skills com confiança acima do threshold."""
        return [s for s in self.hard_skills if s.confidence >= min_confidence]

    def has_low_confidence_warning(self) -> bool:
        """True se algum campo crítico tem confiança abaixo de 0.6."""
        return (
            self.experience_confidence < 0.6
            or self.seniority_confidence < 0.6
            or self.skills_confidence < 0.6
        )