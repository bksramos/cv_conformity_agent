from __future__ import annotations
from models.cv_model import CVProfile
from models.jd_model import JobDescription
from models.verdict import LanguageProficiency

PROFICIENCY_ORDER = [
    LanguageProficiency.BASICO,
    LanguageProficiency.INTERMEDIARIO,
    LanguageProficiency.AVANCADO,
    LanguageProficiency.FLUENTE,
    LanguageProficiency.NATIVO,
]


class LanguageValidator:

    def validate(self, cv: CVProfile, jd: JobDescription) -> dict:
        if not jd.languages_required:
            return {"score": 100.0, "has_blocker": False,
                    "matched": ["Sem requisito de idioma"], "missing": [], "notes": []}

        matched, missing, notes = [], [], []
        scores = []

        for req_lang in jd.languages_required:
            cv_lang = next(
                (l for l in cv.languages if l.name.lower() == req_lang.name.lower()),
                None
            )
            if not cv_lang:
                missing.append(f"{req_lang.name} ({req_lang.proficiency.value})")
                scores.append(0.0)
                continue

            req_idx = PROFICIENCY_ORDER.index(req_lang.proficiency)
            cv_idx  = PROFICIENCY_ORDER.index(cv_lang.proficiency)

            if cv_idx >= req_idx:
                matched.append(f"{req_lang.name}: {cv_lang.proficiency.value}")
                scores.append(1.0)
            elif cv_idx == req_idx - 1:
                matched.append(f"{req_lang.name}: {cv_lang.proficiency.value} (abaixo do ideal)")
                scores.append(0.6)
                notes.append(f"{req_lang.name} requer {req_lang.proficiency.value}, candidato tem {cv_lang.proficiency.value}")
            else:
                missing.append(f"{req_lang.name}: nível insuficiente")
                scores.append(0.2)

        score = (sum(scores) / len(scores)) * 100 if scores else 100.0
        return {
            "score": round(score, 1),
            "has_blocker": False,
            "matched": matched,
            "missing": missing,
            "partial": [],
            "notes": notes,
        }
    
    #c489aff0-80f6-4a43-b1cf-a7d410ee1edc