# ============================================================
# Orquestra todos os validators e produz o ConformityResult
# ============================================================
from __future__ import annotations
from loguru import logger

from models.cv_model import CVProfile
from models.jd_model import JobDescription
from models.conformity_result import ConformityResult
from models.verdict import Verdict
from validators.skills_validator import SkillsValidator
from validators.experience_validator import ExperienceValidator
from validators.education_validator import EducationValidator
from validators.language_validator import LanguageValidator
from scoring.matching_score import MatchingScore, THRESHOLD_APPROVED, THRESHOLD_PARTIAL
from config.settings import settings


class ConformityValidator:

    def __init__(self):
        self._skills  = SkillsValidator()
        self._exp     = ExperienceValidator()
        self._edu     = EducationValidator()
        self._lang    = LanguageValidator()
        self._scoring = MatchingScore()

    def validate(self, cv: CVProfile, jd: JobDescription) -> ConformityResult:
        logger.info(
            f"[ConformityValidator] Iniciando | "
            f"candidato='{cv.candidate_name}' × vaga='{jd.title}'"
        )

        # ── Log do estado do CV ───────────────────────────────────────────
        logger.debug(
            f"[ConformityValidator] CV summary | "
            f"skills={len(cv.hard_skills)} | "
            f"exp_years={cv.total_experience_years} (src={cv.experience_source}) | "
            f"seniority={cv.seniority_inferred.value} (conf={cv.seniority_confidence:.2f}) | "
            f"edu={len(cv.education)} | lang={len(cv.languages)} | "
            f"overall_conf={cv.extraction_confidence:.2f}"
        )
        if cv.hard_skills:
            skills_summary = ", ".join(
                f"{s.name}({s.confidence:.0%})" for s in cv.hard_skills[:10]
            )
            logger.debug(f"[ConformityValidator] CV skills (top 10): [{skills_summary}]")
        else:
            logger.warning("[ConformityValidator] ⚠ CV sem hard_skills — dimensão skills será 0")

        # ── Log do estado da JD ───────────────────────────────────────────
        logger.debug(
            f"[ConformityValidator] JD summary | "
            f"required_skills={len(jd.required_skills)} | "
            f"min_exp={jd.min_experience_years}a | "
            f"seniority={jd.seniority.value} | "
            f"edu_req={len(jd.education_requirements)} | "
            f"lang_req={len(jd.languages_required)}"
        )
        if jd.required_skills:
            req_summary = ", ".join(
                f"{s.name}({'OBR' if s.is_required else 'DES'}|{s.confidence:.0%})"
                for s in jd.required_skills[:10]
            )
            logger.debug(f"[ConformityValidator] JD skills (top 10): [{req_summary}]")
        else:
            logger.warning("[ConformityValidator] ⚠ JD sem required_skills — dimensão skills será 0")

        # ── Aviso de baixa confiança antes de validar ─────────────────────
        if cv.has_low_confidence_warning():
            logger.warning(
                f"[ConformityValidator] ⚠ CV com baixa confiança de extração | "
                f"exp_conf={cv.experience_confidence:.2f} | "
                f"seniority_conf={cv.seniority_confidence:.2f} | "
                f"skills_conf={cv.skills_confidence:.2f} — "
                f"resultados podem ser imprecisos"
            )
        if jd.has_low_confidence_warning():
            logger.warning(
                f"[ConformityValidator] ⚠ JD com baixa confiança de extração | "
                f"skills_conf={jd.skills_confidence:.2f} — "
                f"resultados podem ser imprecisos"
            )

        # ── Validators ────────────────────────────────────────────────────
        logger.debug("[ConformityValidator] Rodando SkillsValidator...")
        skills_r = self._skills.validate(cv, jd)
        logger.debug(
            f"[ConformityValidator] SkillsValidator resultado | "
            f"matched={skills_r.get('matched', [])} | "
            f"missing={skills_r.get('missing', [])} | "
            f"partial={skills_r.get('partial', [])} | "
            f"score_raw={skills_r.get('score')}"
        )

        logger.debug("[ConformityValidator] Rodando ExperienceValidator...")
        exp_r = self._exp.validate(cv, jd)
        logger.debug(
            f"[ConformityValidator] ExperienceValidator resultado | "
            f"matched={exp_r.get('matched', [])} | "
            f"missing={exp_r.get('missing', [])} | "
            f"score_raw={exp_r.get('score')}"
        )

        logger.debug("[ConformityValidator] Rodando EducationValidator...")
        edu_r = self._edu.validate(cv, jd)
        logger.debug(
            f"[ConformityValidator] EducationValidator resultado | "
            f"matched={edu_r.get('matched', [])} | "
            f"missing={edu_r.get('missing', [])} | "
            f"score_raw={edu_r.get('score')}"
        )

        logger.debug("[ConformityValidator] Rodando LanguageValidator...")
        lang_r = self._lang.validate(cv, jd)
        logger.debug(
            f"[ConformityValidator] LanguageValidator resultado | "
            f"matched={lang_r.get('matched', [])} | "
            f"missing={lang_r.get('missing', [])} | "
            f"score_raw={lang_r.get('score')}"
        )

        # ── Scoring ───────────────────────────────────────────────────────
        logger.debug("[ConformityValidator] Calculando score final...")
        try:
            overall, dims, has_blocker = self._scoring.calculate(
                skills_r, exp_r, edu_r, lang_r
            )
        except Exception as e:
            logger.error(f"[ConformityValidator] ❌ Erro no MatchingScore.calculate: {e}", exc_info=True)
            raise

        # ── Log das dimensões produzidas ──────────────────────────────────
        if dims:
            logger.debug(
                f"[ConformityValidator] Dimensões calculadas | "
                f"hard_skills={dims.hard_skills.score if dims.hard_skills else 'N/A'} | "
                f"experience={dims.experience.score if dims.experience else 'N/A'} | "
                f"education={dims.education.score if dims.education else 'N/A'} | "
                f"languages={dims.languages.score if dims.languages else 'N/A'}"
            )
            # Verificação de sanidade — avisa se alguma dimensão é None
            for dim_name in ("hard_skills", "experience", "education", "languages", "soft_skills"):
                dim_obj = getattr(dims, dim_name, None)
                if dim_obj is None:
                    logger.warning(
                        f"[ConformityValidator] ⚠ Dimensão '{dim_name}' é None — "
                        f"_dims_to_out retornará campos vazios para esta dimensão"
                    )
        else:
            logger.error(
                "[ConformityValidator] ❌ dims é None após MatchingScore.calculate — "
                "a UI mostrará dimensões vazias"
            )

        # ── Resultado ─────────────────────────────────────────────────────
        critical_gaps = (
            skills_r.get("missing", []) +
            exp_r.get("missing", []) +
            lang_r.get("missing", [])
        )
        strengths = (
            skills_r.get("matched", [])[:5] +
            exp_r.get("matched", [])
        )
        partial = skills_r.get("partial", [])

        result = ConformityResult(
            cv_hash              = cv.pdf_hash,
            jd_id                = jd.id,
            candidate_name       = cv.candidate_name,
            jd_title             = jd.title,
            overall_score        = overall,
            dimensions           = dims,
            critical_gaps        = critical_gaps,
            strengths            = strengths,
            partial_matches      = partial,
            has_absolute_blocker = has_blocker,
            llm_model_used       = settings.ollama_model,
        )
        result.set_verdict_from_score(THRESHOLD_APPROVED, THRESHOLD_PARTIAL)

        logger.info(
            f"[ConformityValidator] ✅ Validação concluída | "
            f"score={overall:.1f} | veredito={result.verdict.value} | "
            f"bloqueador={has_blocker} | "
            f"skills={dims.hard_skills.score if dims and dims.hard_skills else 0:.1f} | "
            f"exp={dims.experience.score if dims and dims.experience else 0:.1f} | "
            f"edu={dims.education.score if dims and dims.education else 0:.1f} | "
            f"lang={dims.languages.score if dims and dims.languages else 0:.1f} | "
            f"gaps={len(critical_gaps)} | strengths={len(strengths)}"
        )
        return result