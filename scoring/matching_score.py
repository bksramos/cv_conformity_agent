from __future__ import annotations
from models.conformity_result import ConformityDimensions, DimensionScore
from config.feature_flags import flags

# Pesos de cada dimensão no score final (devem somar 1.0)
DIMENSION_WEIGHTS = {
    "hard_skills": 0.40,
    "experience":  0.30,
    "education":   0.15,
    "languages":   0.10,
    "soft_skills": 0.05,
}

# Thresholds de veredito
THRESHOLD_APPROVED = 70.0
THRESHOLD_PARTIAL  = 50.0


class MatchingScore:

    def calculate(
        self,
        skills_result:   dict,
        experience_result: dict,
        education_result:  dict,
        language_result:   dict,
    ) -> tuple[float, ConformityDimensions, bool]:
        """
        Calcula o score final ponderado e monta o ConformityDimensions.
        Retorna: (overall_score, dimensions, has_absolute_blocker)
        """
        dims = ConformityDimensions(
            hard_skills=DimensionScore(
                score=skills_result["score"],
                weight=DIMENSION_WEIGHTS["hard_skills"],
                matched=skills_result.get("matched", []),
                missing=skills_result.get("missing", []),
                partial=skills_result.get("partial", []),
                is_blocked=skills_result.get("has_blocker", False),
            ),
            experience=DimensionScore(
                score=experience_result["score"],
                weight=DIMENSION_WEIGHTS["experience"],
                matched=experience_result.get("matched", []),
                missing=experience_result.get("missing", []),
                notes=experience_result.get("notes", []),
            ),
            education=DimensionScore(
                score=education_result["score"],
                weight=DIMENSION_WEIGHTS["education"],
                matched=education_result.get("matched", []),
                missing=education_result.get("missing", []),
            ),
            languages=DimensionScore(
                score=language_result["score"],
                weight=DIMENSION_WEIGHTS["languages"],
                matched=language_result.get("matched", []),
                missing=language_result.get("missing", []),
                notes=language_result.get("notes", []),
            ),
            soft_skills=DimensionScore(
                score=100.0,   # Fase 2 do produto
                weight=DIMENSION_WEIGHTS["soft_skills"],
            ),
        )

        # Score ponderado
        active_dims = {
            "hard_skills": dims.hard_skills.score if flags.VALIDATE_HARD_SKILLS    else None,
            "experience":  dims.experience.score  if flags.VALIDATE_EXPERIENCE_YEARS else None,
            "education":   dims.education.score   if flags.VALIDATE_EDUCATION       else None,
            "languages":   dims.languages.score   if flags.VALIDATE_LANGUAGES       else None,
            "soft_skills": dims.soft_skills.score if flags.VALIDATE_SOFT_SKILLS     else None,
        }

        total_weight = sum(
            DIMENSION_WEIGHTS[k] for k, v in active_dims.items() if v is not None
        )
        weighted_sum = sum(
            v * DIMENSION_WEIGHTS[k]
            for k, v in active_dims.items() if v is not None
        )
        overall = (weighted_sum / total_weight) if total_weight > 0 else 0.0

        has_blocker = dims.hard_skills.is_blocked

        return round(overall, 1), dims, has_blocker
