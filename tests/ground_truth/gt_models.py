# ============================================================
# Ground Truth com contrato de confiança — Fase 6
# ============================================================
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

GT_DIR          = Path(__file__).parent
CVS_DIR         = GT_DIR / "cvs"
JDS_DIR         = GT_DIR / "jds"
RESULTS_FILE    = GT_DIR / "expected_results.json"
ANNOTATIONS_DIR = GT_DIR / "annotations"

VALID_VERDICTS = {"APROVADO", "APROVADO_COM_RESSALVAS", "REPROVADO"}
DIMENSIONS     = ("hard_skills", "experience", "education", "languages")


# ─────────────────────────────────────────────────────────────────────────────
# Anotação de skill com contrato de confiança
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SkillExpectation:
    """
    Uma skill esperada com o nível mínimo de confiança que o agent deve reportar.
    Permite distinguir "essa skill deve ser encontrada com certeza" de
    "essa skill pode aparecer com confiança baixa".
    """
    name: str
    min_confidence: float = 0.7   # limiar para considerar detecção válida
    expected_source: Optional[str] = None  # "explicit" | "inferred_from_exp" | qualquer

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SkillExpectation":
        if isinstance(d, str):
            # Compatibilidade retroativa: string simples → SkillExpectation padrão
            return cls(name=d)
        return cls(
            name=d.get("name", ""),
            min_confidence=d.get("min_confidence", 0.7),
            expected_source=d.get("expected_source"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Anotação por dimensão com thresholds de confiança
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DimensionAnnotation:
    """
    Anotação manual para uma dimensão do matching.

    expected_skills_present / expected_skills_absent:
        Skills com o nível de confiança mínimo esperado para cada uma.

    expected_score_min/max: faixa aceitável para o score da dimensão.

    min_dimension_confidence: confiança mínima que o campo extraído deve ter
        para que o resultado seja considerado válido (ex: experience_confidence ≥ 0.7).
    """
    expected_skills_present:     list[SkillExpectation] = field(default_factory=list)
    expected_skills_absent:      list[str]              = field(default_factory=list)
    expected_score_min:          float = 0.0
    expected_score_max:          float = 100.0
    min_dimension_confidence:    float = 0.6   # threshold para considerar extração confiável
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["expected_skills_present"] = [s.to_dict() for s in self.expected_skills_present]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DimensionAnnotation":
        skills_present = [
            SkillExpectation.from_dict(s)
            for s in d.get("expected_skills_present", [])
        ]
        return cls(
            expected_skills_present  = skills_present,
            expected_skills_absent   = d.get("expected_skills_absent", []),
            expected_score_min       = d.get("expected_score_min", 0.0),
            expected_score_max       = d.get("expected_score_max", 100.0),
            min_dimension_confidence = d.get("min_dimension_confidence", 0.6),
            notes                    = d.get("notes", ""),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Expectativas de confiança do CVProfile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractionContractExpectation:
    """
    Define os thresholds mínimos que a extração deve atingir para o caso ser considerado válido.
    Análogo ao SLA de qualidade da extração — não do resultado final.
    """
    min_extraction_confidence:    float = 0.6
    min_seniority_confidence:     float = 0.6
    min_experience_confidence:    float = 0.6
    min_skills_confidence:        float = 0.6

    expected_seniority:           Optional[str]  = None  # ex: "SENIOR"
    expected_total_years_min:     Optional[float] = None
    expected_total_years_max:     Optional[float] = None
    expected_seniority_source:    Optional[str]  = None  # ex: "cross_validated"

    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExtractionContractExpectation":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─────────────────────────────────────────────────────────────────────────────
# Caso de teste
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GroundTruthCase:
    """
    Um par (CV, JD) com resultado esperado e contratos de confiança anotados.

    cv_filename: nome do PDF em tests/ground_truth/cvs/
    jd_source:   'file' → usa jd_filename em tests/ground_truth/jds/
                 'db'   → usa jd_id (UUID no PostgreSQL)
    """
    id:                        str
    cv_filename:               str
    jd_source:                 str           # 'file' | 'db'
    expected_verdict:          str           # APROVADO | APROVADO_COM_RESSALVAS | REPROVADO
    expected_score_min:        float
    expected_score_max:        float
    expected_absolute_blocker: bool                               = False
    jd_filename:               Optional[str]                      = None
    jd_id:                     Optional[str]                      = None
    annotations:               dict[str, DimensionAnnotation]     = field(default_factory=dict)
    extraction_contract:       Optional[ExtractionContractExpectation] = None
    notes:                     str                                = ""
    annotated_by:              str                                = ""
    annotated_at:              str                                = ""

    def validate(self) -> list[str]:
        errs = []
        if self.expected_verdict not in VALID_VERDICTS:
            errs.append(f"[{self.id}] Veredito inválido: {self.expected_verdict!r}")
        if not (0 <= self.expected_score_min <= self.expected_score_max <= 100):
            errs.append(f"[{self.id}] Score range inválido: [{self.expected_score_min}, {self.expected_score_max}]")
        if self.jd_source == "file" and not self.jd_filename:
            errs.append(f"[{self.id}] jd_source='file' mas jd_filename não definido")
        if self.jd_source == "db" and not self.jd_id:
            errs.append(f"[{self.id}] jd_source='db' mas jd_id não definido")
        cv_path = CVS_DIR / self.cv_filename
        if not cv_path.exists():
            errs.append(f"[{self.id}] CV não encontrado: {cv_path}")
        if self.jd_source == "file" and self.jd_filename:
            jd_path = JDS_DIR / self.jd_filename
            if not jd_path.exists():
                errs.append(f"[{self.id}] JD não encontrada: {jd_path}")
        return errs

    def to_dict(self) -> dict:
        d = asdict(self)
        d["annotations"] = {k: v.to_dict() for k, v in self.annotations.items()}
        d["extraction_contract"] = (
            self.extraction_contract.to_dict() if self.extraction_contract else None
        )
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GroundTruthCase":
        annotations = {
            k: DimensionAnnotation.from_dict(v)
            for k, v in d.get("annotations", {}).items()
        }
        ec_raw = d.get("extraction_contract")
        extraction_contract = ExtractionContractExpectation.from_dict(ec_raw) if ec_raw else None

        return cls(
            id                        = d["id"],
            cv_filename               = d["cv_filename"],
            jd_source                 = d.get("jd_source", "file"),
            expected_verdict          = d["expected_verdict"],
            expected_score_min        = d["expected_score_min"],
            expected_score_max        = d["expected_score_max"],
            expected_absolute_blocker = d.get("expected_absolute_blocker", False),
            jd_filename               = d.get("jd_filename"),
            jd_id                     = d.get("jd_id"),
            annotations               = annotations,
            extraction_contract       = extraction_contract,
            notes                     = d.get("notes", ""),
            annotated_by              = d.get("annotated_by", ""),
            annotated_at              = d.get("annotated_at", ""),
        )

    @property
    def cv_path(self) -> Path:
        return CVS_DIR / self.cv_filename

    @property
    def jd_path(self) -> Optional[Path]:
        return (JDS_DIR / self.jd_filename) if self.jd_filename else None

    def cv_hash(self) -> str:
        return hashlib.sha256(self.cv_path.read_bytes()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# I/O
# ─────────────────────────────────────────────────────────────────────────────

def load_cases(path: Path = RESULTS_FILE) -> list[GroundTruthCase]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [GroundTruthCase.from_dict(c) for c in raw]


def save_cases(cases: list[GroundTruthCase], path: Path = RESULTS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([c.to_dict() for c in cases], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_or_replace_case(case: GroundTruthCase, path: Path = RESULTS_FILE) -> None:
    cases = load_cases(path)
    cases = [c for c in cases if c.id != case.id]
    cases.append(case)
    cases.sort(key=lambda c: c.id)
    save_cases(cases, path)