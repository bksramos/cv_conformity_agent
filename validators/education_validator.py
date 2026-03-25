from __future__ import annotations
import re
from models.cv_model import CVProfile
from models.jd_model import JobDescription

DEGREE_LEVELS = {
    "técnico": 1, "tecnólogo": 2, "bacharelado": 3, "licenciatura": 3,
    "pós-graduação": 4, "especialização": 4, "mba": 4,
    "mestrado": 5, "doutorado": 6,
}


class EducationValidator:

    def validate(self, cv: CVProfile, jd: JobDescription) -> dict:
        if not jd.education_requirements:
            return {"score": 100.0, "has_blocker": False,
                    "matched": ["Sem requisito de formação"], "missing": [], "notes": []}

        score, matched, missing, notes = 100.0, [], [], []

        # Valida formação acadêmica
        edu_score, edu_note = self._validate_degree(cv, jd)
        score = min(score, edu_score)
        notes.append(edu_note)
        (matched if edu_score >= 70 else missing).append(edu_note)

        # Valida certificações requeridas
        if jd.certifications_required:
            cert_score, cert_note = self._validate_certifications(cv, jd)
            score = (score + cert_score) / 2
            notes.append(cert_note)
            (matched if cert_score >= 70 else missing).append(cert_note)

        return {
            "score": round(score, 1),
            "has_blocker": False,
            "matched": matched,
            "missing": missing,
            "partial": [],
            "notes": notes,
        }

    def _validate_degree(self, cv: CVProfile, jd: JobDescription) -> tuple[float, str]:
        req_text = " ".join(jd.education_requirements).lower()
        cv_degrees = [e.degree.lower() for e in cv.education if e.is_complete]

        if not cv_degrees:
            return 50.0, "Formação acadêmica não identificada no currículo"

        req_level = 0
        for degree, level in DEGREE_LEVELS.items():
            if degree in req_text:
                req_level = max(req_level, level)

        if req_level == 0:
            return 100.0, "Requisito de formação não estruturado — não penalizado"

        cv_level = max(
            (DEGREE_LEVELS.get(d, 0) for d in cv_degrees),
            default=0
        )
        if cv_level >= req_level:
            return 100.0, f"Formação atende o requisito"
        if cv_level == req_level - 1:
            return 70.0, "Formação levemente abaixo do requerido"
        return 40.0, "Formação abaixo do requerido"

    def _validate_certifications(self, cv: CVProfile, jd: JobDescription) -> tuple[float, str]:
        cv_certs = {c.lower() for c in cv.certifications}
        matched  = 0
        for req_cert in jd.certifications_required:
            if any(req_cert.lower() in c for c in cv_certs):
                matched += 1
        ratio = matched / len(jd.certifications_required)
        score = ratio * 100
        return score, f"{matched}/{len(jd.certifications_required)} certificações encontradas"
