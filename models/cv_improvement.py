from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "critical"   # impede extração correta — deve ser corrigido
    WARNING  = "warning"    # reduz confiança significativamente
    INFO     = "info"       # melhoria desejável mas não crítica


SEVERITY_SCORE_PENALTY = {
    Severity.CRITICAL: 20,
    Severity.WARNING:  10,
    Severity.INFO:      4,
}


# ── Diagnóstico ───────────────────────────────────────────────────────────────

@dataclass
class DiagnosticIssue:
    section:        str        # "experience" | "skills" | "languages" | "seniority" | "general"
    severity:       Severity
    title:          str
    description:    str
    action:         str        # instrução direta ao candidato
    affected_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "section":        self.section,
            "severity":       self.severity.value,
            "title":          self.title,
            "description":    self.description,
            "action":         self.action,
            "affected_items": self.affected_items,
        }


@dataclass
class CVDiagnosis:
    issues:                list[DiagnosticIssue]
    cv_quality_score:      float   # 0–100 — qualidade estrutural do CV
    is_ready_for_matching: bool    # False se há issues críticos ou conf < 0.6
    summary:               str

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.INFO)

    @property
    def by_section(self) -> dict[str, list[DiagnosticIssue]]:
        grouped: dict[str, list[DiagnosticIssue]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.section, []).append(issue)
        return grouped

    def to_dict(self) -> dict:
        return {
            "cv_quality_score":      self.cv_quality_score,
            "is_ready_for_matching": self.is_ready_for_matching,
            "summary":               self.summary,
            "critical_count":        self.critical_count,
            "warning_count":         self.warning_count,
            "info_count":            self.info_count,
            "issues":                [i.to_dict() for i in self.issues],
        }


# ── Melhorias de clareza ──────────────────────────────────────────────────────

@dataclass
class ImprovedSection:
    section:        str        # "summary" | "experience" | nome da empresa
    role:           str = ""   # cargo (para experiências)
    original:       str = ""
    improved:       str = ""
    changes_made:   list[str] = field(default_factory=list)
    keywords_added: list[str] = field(default_factory=list)
    # Sempre True — garantia de que o agent não inventou nada
    # Se o LLM sinalizar insegurança, a seção não é incluída
    certified_honest: bool = True

    def to_dict(self) -> dict:
        return {
            "section":          self.section,
            "role":             self.role,
            "original":         self.original,
            "improved":         self.improved,
            "changes_made":     self.changes_made,
            "keywords_added":   self.keywords_added,
            "certified_honest": self.certified_honest,
        }


@dataclass
class CVImprovementResult:
    diagnosis:         CVDiagnosis
    improved_sections: list[ImprovedSection]
    jd_title:          Optional[str]   = None
    general_tips:      list[str]       = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "diagnosis":         self.diagnosis.to_dict(),
            "jd_title":          self.jd_title,
            "general_tips":      self.general_tips,
            "improved_sections": [s.to_dict() for s in self.improved_sections],
        }
