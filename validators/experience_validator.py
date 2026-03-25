from __future__ import annotations
from models.cv_model import CVProfile
from models.jd_model import JobDescription
from models.verdict import SeniorityLevel

# Mapa de anos mínimos esperados por nível
SENIORITY_YEARS: dict[SeniorityLevel, tuple[float, float]] = {
    SeniorityLevel.ESTAGIO:     (0.0, 1.0),
    SeniorityLevel.JUNIOR:      (0.5, 2.0),
    SeniorityLevel.PLENO:       (2.0, 5.0),
    SeniorityLevel.SENIOR:      (5.0, 10.0),
    SeniorityLevel.ESPECIALISTA:(7.0, 99.0),
    SeniorityLevel.LIDERANCA:   (6.0, 99.0),
}


class ExperienceValidator:

    def validate(self, cv: CVProfile, jd: JobDescription) -> dict:
        score     = 100.0
        matched, missing, notes = [], [], []

        # 1. Anos mínimos de experiência
        years_score, years_note = self._validate_years(cv, jd)
        score = min(score, years_score)
        notes.append(years_note)

        # 2. Senioridade
        sen_score, sen_note = self._validate_seniority(cv, jd)
        score = (score + sen_score) / 2
        notes.append(sen_note)

        if years_score >= 80:
            matched.append(f"{cv.total_experience_years} anos de experiência")
        else:
            missing.append(f"Mínimo {jd.min_experience_years} anos requerido")

        if sen_score >= 80:
            matched.append(f"Senioridade {cv.seniority_inferred.value}")
        else:
            missing.append(f"Senioridade requerida: {jd.seniority.value}")

        return {
            "score": round(score, 1),
            "has_blocker": False,
            "matched": matched,
            "missing": missing,
            "partial": [],
            "notes": notes,
        }

    def _validate_years(self, cv: CVProfile, jd: JobDescription) -> tuple[float, str]:
        cv_years  = cv.total_experience_years
        min_years = jd.min_experience_years
        max_years = jd.max_experience_years

        if min_years == 0:
            return 100.0, "Sem requisito mínimo de anos"

        if cv_years >= min_years:
            # Verifica teto (ex: vaga que pede "até 5 anos" para não pagar sênior)
            if max_years and cv_years > max_years * 1.5:
                return 60.0, f"Candidato pode estar acima do nível ({cv_years:.1f}a vs max {max_years}a)"
            return 100.0, f"{cv_years:.1f} anos atende o mínimo de {min_years}"

        ratio = cv_years / min_years
        if ratio >= 0.8:
            return 70.0, f"{cv_years:.1f} anos (próximo do mínimo de {min_years})"
        if ratio >= 0.6:
            return 40.0, f"{cv_years:.1f} anos (abaixo do mínimo de {min_years})"
        return 20.0, f"{cv_years:.1f} anos (muito abaixo do mínimo de {min_years})"

    def _validate_seniority(self, cv: CVProfile, jd: JobDescription) -> tuple[float, str]:
        cv_sen  = cv.seniority_inferred
        jd_sen  = jd.seniority

        if jd_sen == SeniorityLevel.NAO_INFORMADO:
            return 100.0, "Senioridade não especificada na vaga"
        if cv_sen == SeniorityLevel.NAO_INFORMADO:
            return 70.0, "Senioridade do candidato não identificada"
        if cv_sen == jd_sen:
            return 100.0, f"Senioridade exata: {cv_sen.value}"

        levels = list(SeniorityLevel)
        try:
            cv_idx = levels.index(cv_sen)
            jd_idx = levels.index(jd_sen)
            diff   = abs(cv_idx - jd_idx)
            if diff == 1:
                return 75.0, f"Senioridade próxima: {cv_sen.value} vs {jd_sen.value}"
            return 40.0, f"Senioridade distante: {cv_sen.value} vs {jd_sen.value}"
        except ValueError:
            return 60.0, "Não foi possível comparar senioridades"
