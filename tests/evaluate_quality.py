#!/usr/bin/env python3
# ============================================================
# FILE: tests/evaluate_quality.py
# Runner de avaliação de qualidade com contrato de confiança — Fase 6
#
# Uso:
#   python tests/evaluate_quality.py                        # todos os casos
#   python tests/evaluate_quality.py --cases case_001,case_002
#   python tests/evaluate_quality.py --output relatorio.md
#   python tests/evaluate_quality.py --verbose
#   python tests/evaluate_quality.py --dry-run
#   python tests/evaluate_quality.py --contract-only        # só avalia extração, não veredito
# ============================================================
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.ground_truth.gt_models import (
    DIMENSIONS,
    RESULTS_FILE,
    ExtractionContractExpectation,
    GroundTruthCase,
    SkillExpectation,
    load_cases,
)

API_BASE    = "http://localhost:8000/api/v1"
REPORTS_DIR = Path(__file__).parent / "ground_truth" / "reports"
TIMEOUT_SEC = 300


# ─────────────────────────────────────────────────────────────────────────────
# Resultado da avaliação do contrato de confiança
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContractEvaluation:
    """Resultado da checagem do contrato de confiança de extração."""
    overall_confidence_ok:    Optional[bool] = None
    seniority_confidence_ok:  Optional[bool] = None
    experience_confidence_ok: Optional[bool] = None
    skills_confidence_ok:     Optional[bool] = None
    seniority_correct:        Optional[bool] = None
    years_in_range:           Optional[bool] = None
    seniority_source_correct: Optional[bool] = None

    actual_extraction_confidence: Optional[float] = None
    actual_seniority_confidence:  Optional[float] = None
    actual_experience_confidence: Optional[float] = None
    actual_skills_confidence:     Optional[float] = None
    actual_seniority:             Optional[str]   = None
    actual_total_years:           Optional[float] = None
    actual_seniority_source:      Optional[str]   = None

    contract_score: float = 0.0   # 0–1, proporção de checks passados
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Resultado por caso
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case_id:               str
    cv_filename:           str
    expected_verdict:      str
    actual_verdict:        Optional[str]   = None
    expected_score_min:    float           = 0.0
    expected_score_max:    float           = 100.0
    actual_score:          Optional[float] = None
    expected_blocker:      bool            = False
    actual_blocker:        Optional[bool]  = None
    dimension_scores:      dict[str, float] = field(default_factory=dict)
    dimension_confidences: dict[str, float] = field(default_factory=dict)
    skill_metrics:         dict             = field(default_factory=dict)
    contract_eval:         Optional[ContractEvaluation] = None
    elapsed_sec:           float           = 0.0
    cache_hit:             bool            = False
    error:                 Optional[str]   = None

    @property
    def verdict_correct(self) -> Optional[bool]:
        return None if self.actual_verdict is None else self.actual_verdict == self.expected_verdict

    @property
    def score_in_range(self) -> Optional[bool]:
        return None if self.actual_score is None else (
            self.expected_score_min <= self.actual_score <= self.expected_score_max
        )

    @property
    def blocker_correct(self) -> Optional[bool]:
        return None if self.actual_blocker is None else self.actual_blocker == self.expected_blocker

    @property
    def ok(self) -> bool:
        return self.error is None


# ─────────────────────────────────────────────────────────────────────────────
# Relatório agregado
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EvaluationReport:
    run_at:            str
    total_cases:       int
    executed:          int
    skipped:           int
    errors:            int

    # Métricas de output (veredito final)
    verdict_accuracy:  float
    score_calibration: float
    blocker_accuracy:  float
    avg_skill_f1:      float

    # Métricas do contrato de confiança (extração intermediária)
    avg_contract_score:       float   # média do contract_score entre casos
    contract_confidence_rate: float   # % de casos onde todos os thresholds foram atingidos
    seniority_accuracy:       float   # % de casos onde seniority foi extraída corretamente
    years_accuracy:           float   # % de casos onde total_years estava no range esperado

    per_case:      list[CaseResult]
    per_dimension: dict

    # Overall ponderado: 50% output + 50% contrato de confiança
    overall_quality: float

    def to_dict(self) -> dict:
        return {
            "run_at":             self.run_at,
            "total_cases":        self.total_cases,
            "executed":           self.executed,
            "errors":             self.errors,
            "verdict_accuracy":   round(self.verdict_accuracy,        4),
            "score_calibration":  round(self.score_calibration,       4),
            "blocker_accuracy":   round(self.blocker_accuracy,        4),
            "avg_skill_f1":       round(self.avg_skill_f1,            4),
            "avg_contract_score": round(self.avg_contract_score,      4),
            "contract_conf_rate": round(self.contract_confidence_rate, 4),
            "seniority_accuracy": round(self.seniority_accuracy,      4),
            "years_accuracy":     round(self.years_accuracy,          4),
            "overall_quality":    round(self.overall_quality,         2),
            "per_dimension":      {
                k: {kk: round(vv, 4) for kk, vv in v.items()}
                for k, v in self.per_dimension.items()
            },
            "per_case": [
                {
                    "id":               r.case_id,
                    "cv":               r.cv_filename,
                    "expected_verdict": r.expected_verdict,
                    "actual_verdict":   r.actual_verdict,
                    "verdict_correct":  r.verdict_correct,
                    "score_range":      [r.expected_score_min, r.expected_score_max],
                    "actual_score":     r.actual_score,
                    "score_in_range":   r.score_in_range,
                    "blocker_correct":  r.blocker_correct,
                    "contract_score":   round(r.contract_eval.contract_score, 3) if r.contract_eval else None,
                    "elapsed_sec":      round(r.elapsed_sec, 2),
                    "cache_hit":        r.cache_hit,
                    "error":            r.error,
                    "skill_metrics":    r.skill_metrics,
                }
                for r in self.per_case
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Chamada à API
# ─────────────────────────────────────────────────────────────────────────────

def _call_api(case: GroundTruthCase) -> tuple[dict, float]:
    pdf_bytes = case.cv_path.read_bytes()
    data: dict = {}
    if case.jd_source == "db":
        data["jd_id"] = case.jd_id
    else:
        jd_raw = case.jd_path.read_text(encoding="utf-8")
        jd_obj = json.loads(jd_raw)
        data["jd_text"] = jd_obj.get("raw_text") or json.dumps(jd_obj, ensure_ascii=False)

    files = {"pdf": (case.cv_filename, pdf_bytes, "application/pdf")}
    t0 = time.perf_counter()
    with httpx.Client(timeout=TIMEOUT_SEC) as client:
        resp = client.post(f"{API_BASE}/analyze", data=data, files=files)
        resp.raise_for_status()
    return resp.json(), time.perf_counter() - t0


# ─────────────────────────────────────────────────────────────────────────────
# Métricas de skills — confidence-aware
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return s.strip().lower()


def _skill_metrics(
    expected: list[SkillExpectation],
    actual_skills: list[dict],   # lista de dicts do CVProfile.hard_skills
) -> dict:
    """
    Compara skills esperadas com as extraídas, levando em conta confidence mínima.

    Uma skill é considerada "detectada" se:
    1. Seu nome (case-insensitive) aparece em actual_skills
    2. A confidence do actual está acima do min_confidence da expectation
    """
    act_by_name: dict[str, dict] = {
        _normalize(s.get("name", "")): s for s in actual_skills
    }

    tp, fp, fn = 0, 0, 0
    low_confidence_hits: list[str] = []   # skill encontrada mas com confidence insuficiente

    for exp in expected:
        key = _normalize(exp.name)
        actual = act_by_name.get(key)
        if actual is None:
            fn += 1  # não encontrada
        elif actual.get("confidence", 1.0) >= exp.min_confidence:
            tp += 1  # encontrada com confiança suficiente
        else:
            fn += 1  # encontrada mas confiança abaixo do esperado
            low_confidence_hits.append(
                f"{exp.name} (expected ≥{exp.min_confidence:.0%}, got {actual.get('confidence', 0):.0%})"
            )

    # FP: skills que o agent retornou mas não estavam no expected
    expected_names = {_normalize(e.name) for e in expected}
    fp = len([n for n in act_by_name if n not in expected_names])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision, "recall": recall, "f1": f1,
        "tp": tp, "fp": fp, "fn": fn,
        "low_confidence_hits": low_confidence_hits,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Avaliação do contrato de confiança
# ─────────────────────────────────────────────────────────────────────────────

def _eval_contract(
    contract: ExtractionContractExpectation,
    cv_profile: dict,
) -> ContractEvaluation:
    result = ContractEvaluation()
    checks_passed, checks_total = 0, 0

    def _check(attr: str, actual: Optional[float], threshold: float) -> bool:
        setattr(result, f"actual_{attr}", actual)
        ok = actual is not None and actual >= threshold
        setattr(result, f"{attr}_ok", ok)
        return ok

    # Confiança global
    checks_total += 1
    if _check(
        "extraction_confidence",
        cv_profile.get("extraction_confidence"),
        contract.min_extraction_confidence,
    ):
        checks_passed += 1

    # Confiança de senioridade
    checks_total += 1
    if _check(
        "seniority_confidence",
        cv_profile.get("seniority_confidence"),
        contract.min_seniority_confidence,
    ):
        checks_passed += 1

    # Confiança de experiência
    checks_total += 1
    if _check(
        "experience_confidence",
        cv_profile.get("experience_confidence"),
        contract.min_experience_confidence,
    ):
        checks_passed += 1

    # Confiança de skills
    checks_total += 1
    if _check(
        "skills_confidence",
        cv_profile.get("skills_confidence"),
        contract.min_skills_confidence,
    ):
        checks_passed += 1

    # Senioridade esperada
    result.actual_seniority = cv_profile.get("seniority_inferred")
    if contract.expected_seniority:
        checks_total += 1
        result.seniority_correct = result.actual_seniority == contract.expected_seniority
        if result.seniority_correct:
            checks_passed += 1
        else:
            result.warnings.append(
                f"Senioridade: esperado {contract.expected_seniority}, "
                f"obtido {result.actual_seniority}"
            )

    # Faixa de anos de experiência
    result.actual_total_years = cv_profile.get("total_experience_years")
    if contract.expected_total_years_min is not None or contract.expected_total_years_max is not None:
        checks_total += 1
        lo = contract.expected_total_years_min or 0
        hi = contract.expected_total_years_max or 99
        result.years_in_range = (
            result.actual_total_years is not None
            and lo <= result.actual_total_years <= hi
        )
        if result.years_in_range:
            checks_passed += 1
        else:
            result.warnings.append(
                f"Anos experiência: esperado [{lo}–{hi}], "
                f"obtido {result.actual_total_years}"
            )

    # Source da senioridade
    result.actual_seniority_source = cv_profile.get("seniority_source")
    if contract.expected_seniority_source:
        checks_total += 1
        result.seniority_source_correct = (
            result.actual_seniority_source == contract.expected_seniority_source
        )
        if result.seniority_source_correct:
            checks_passed += 1

    result.contract_score = checks_passed / checks_total if checks_total > 0 else 0.0
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Avaliação de um caso
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_case(case: GroundTruthCase) -> CaseResult:
    result = CaseResult(
        case_id            = case.id,
        cv_filename        = case.cv_filename,
        expected_verdict   = case.expected_verdict,
        expected_score_min = case.expected_score_min,
        expected_score_max = case.expected_score_max,
        expected_blocker   = case.expected_absolute_blocker,
    )

    errs = case.validate()
    if errs:
        result.error = " | ".join(errs)
        return result

    try:
        api_resp, elapsed = _call_api(case)
    except httpx.ConnectError:
        result.error = "API não está rodando"
        return result
    except httpx.HTTPStatusError as e:
        result.error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        return result
    except Exception as e:
        result.error = str(e)
        return result

    result.elapsed_sec    = elapsed
    result.actual_verdict = api_resp.get("verdict")
    result.actual_score   = api_resp.get("overall_score")
    result.actual_blocker = api_resp.get("has_absolute_blocker", False)
    result.cache_hit      = api_resp.get("cache_hit", False)

    # Campos do CVProfile retornados pela API
    cv_profile = api_resp.get("cv_profile", {})

    # Métricas por dimensão
    dims = api_resp.get("dimensions", {})
    actual_skills = cv_profile.get("hard_skills", [])
    for dim_key in DIMENSIONS:
        dim = dims.get(dim_key, {})
        result.dimension_scores[dim_key]      = dim.get("score", 0.0)
        result.dimension_confidences[dim_key] = dim.get("confidence", 0.0)

        ann = case.annotations.get(dim_key)
        if ann and ann.expected_skills_present and dim_key == "hard_skills":
            result.skill_metrics[dim_key] = _skill_metrics(
                ann.expected_skills_present, actual_skills
            )

    # Avaliação do contrato de confiança
    if case.extraction_contract and cv_profile:
        result.contract_eval = _eval_contract(case.extraction_contract, cv_profile)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Agregação
# ─────────────────────────────────────────────────────────────────────────────

def _mean(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0


def aggregate_metrics(
    results: list[CaseResult],
    cases: list[GroundTruthCase],
) -> EvaluationReport:
    ok = [r for r in results if r.ok]
    n  = len(ok)

    verdict_acc  = _mean([float(r.verdict_correct)  for r in ok if r.verdict_correct  is not None])
    score_cal    = _mean([float(r.score_in_range)   for r in ok if r.score_in_range   is not None])
    blocker_acc  = _mean([float(r.blocker_correct)  for r in ok if r.blocker_correct  is not None])

    # F1 médio de skills
    all_f1 = [
        r.skill_metrics[d]["f1"]
        for r in ok
        for d in DIMENSIONS
        if d in r.skill_metrics
    ]
    avg_f1 = _mean(all_f1)

    # Métricas do contrato de confiança
    contract_scores = [
        r.contract_eval.contract_score
        for r in ok if r.contract_eval
    ]
    avg_contract    = _mean(contract_scores)

    # % de casos onde TODOS os thresholds de confiança foram atingidos (contract_score == 1.0)
    conf_rate = _mean([float(s == 1.0) for s in contract_scores]) if contract_scores else 0.0

    seniority_hits = [
        r.contract_eval.seniority_correct
        for r in ok if r.contract_eval and r.contract_eval.seniority_correct is not None
    ]
    seniority_acc = _mean([float(v) for v in seniority_hits]) if seniority_hits else 0.0

    years_hits = [
        r.contract_eval.years_in_range
        for r in ok if r.contract_eval and r.contract_eval.years_in_range is not None
    ]
    years_acc = _mean([float(v) for v in years_hits]) if years_hits else 0.0

    # Métricas por dimensão
    case_map = {c.id: c for c in cases}
    per_dim: dict[str, dict] = {d: {"precision": [], "recall": [], "f1": [], "score_in_range": [], "confidence": []} for d in DIMENSIONS}
    for r in ok:
        case = case_map.get(r.case_id)
        for dim_key in DIMENSIONS:
            sm = r.skill_metrics.get(dim_key)
            if sm:
                per_dim[dim_key]["precision"].append(sm["precision"])
                per_dim[dim_key]["recall"].append(sm["recall"])
                per_dim[dim_key]["f1"].append(sm["f1"])
            if case:
                ann = case.annotations.get(dim_key)
                if ann and r.dimension_scores.get(dim_key) is not None:
                    in_range = ann.expected_score_min <= r.dimension_scores[dim_key] <= ann.expected_score_max
                    per_dim[dim_key]["score_in_range"].append(float(in_range))
            if r.dimension_confidences.get(dim_key) is not None:
                per_dim[dim_key]["confidence"].append(r.dimension_confidences[dim_key])

    per_dim_agg = {
        d: {
            "precision":      _mean(m["precision"]),
            "recall":         _mean(m["recall"]),
            "f1":             _mean(m["f1"]),
            "score_accuracy": _mean(m["score_in_range"]),
            "avg_confidence": _mean(m["confidence"]),
        }
        for d, m in per_dim.items()
    }

    # Overall: 50% métricas de output + 50% contrato de confiança
    output_score   = verdict_acc * 40 + score_cal * 30 + avg_f1 * 20 + blocker_acc * 10
    contract_score = avg_contract * 50 + conf_rate * 30 + seniority_acc * 10 + years_acc * 10
    overall = output_score * 0.5 + contract_score * 0.5

    return EvaluationReport(
        run_at                   = datetime.now().isoformat(timespec="seconds"),
        total_cases              = len(results),
        executed                 = n,
        skipped                  = len(results) - n,
        errors                   = sum(1 for r in results if r.error),
        verdict_accuracy         = verdict_acc,
        score_calibration        = score_cal,
        blocker_accuracy         = blocker_acc,
        avg_skill_f1             = avg_f1,
        avg_contract_score       = avg_contract,
        contract_confidence_rate = conf_rate,
        seniority_accuracy       = seniority_acc,
        years_accuracy           = years_acc,
        per_case                 = results,
        per_dimension            = per_dim_agg,
        overall_quality          = overall,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Relatório Markdown
# ─────────────────────────────────────────────────────────────────────────────

def _bar(v: float, w: int = 20) -> str:
    filled = int(round(v * w))
    return "█" * filled + "░" * (w - filled)


def generate_markdown(report: EvaluationReport) -> str:
    lines = [
        "# Relatório de Qualidade — CV Conformity Agent",
        f"> Gerado em: {report.run_at}",
        "",
        "## Resumo Executivo",
        "",
        f"| Métrica                      | Valor        | Barra                        |",
        f"|------------------------------|--------------|------------------------------|",
        f"| **Overall Quality**          | **{report.overall_quality:.1f} / 100** | {_bar(report.overall_quality/100)} |",
        f"| Acurácia de Veredito         | {report.verdict_accuracy:.1%}       | {_bar(report.verdict_accuracy)} |",
        f"| Calibração de Score          | {report.score_calibration:.1%}       | {_bar(report.score_calibration)} |",
        f"| F1 Médio de Skills           | {report.avg_skill_f1:.1%}       | {_bar(report.avg_skill_f1)} |",
        f"| Acurácia de Blocker          | {report.blocker_accuracy:.1%}       | {_bar(report.blocker_accuracy)} |",
        f"| **Contract Score Médio**     | **{report.avg_contract_score:.1%}** | {_bar(report.avg_contract_score)} |",
        f"| Contratos 100% atingidos     | {report.contract_confidence_rate:.1%}       | {_bar(report.contract_confidence_rate)} |",
        f"| Acurácia de Senioridade      | {report.seniority_accuracy:.1%}       | {_bar(report.seniority_accuracy)} |",
        f"| Acurácia de Anos Experiência | {report.years_accuracy:.1%}       | {_bar(report.years_accuracy)} |",
        "",
        f"**Casos:** {report.executed} executados / {report.errors} com erro / {report.total_cases} total",
        "",
        "## Métricas por Dimensão",
        "",
        "| Dimensão     | Precision | Recall | F1     | Score Accuracy | Avg Confidence |",
        "|--------------|-----------|--------|--------|----------------|----------------|",
    ]
    for dim, m in report.per_dimension.items():
        lines.append(
            f"| {dim:<12} | {m['precision']:.1%}     | {m['recall']:.1%}  | {m['f1']:.1%} "
            f"| {m['score_accuracy']:.1%}          | {m['avg_confidence']:.1%}           |"
        )

    lines += [
        "",
        "## Contrato de Confiança por Caso",
        "",
        "| ID         | Ext. Conf | Sen. Conf | Exp. Conf | Ski. Conf | Seniority OK | Years OK | Contract |",
        "|------------|-----------|-----------|-----------|-----------|--------------|----------|----------|",
    ]
    for r in report.per_case:
        if not r.contract_eval:
            lines.append(f"| {r.case_id:<10} | — | — | — | — | — | — | (sem contrato) |")
            continue
        ce = r.contract_eval
        def _fmt(v, ok): return f"{v:.0%} {'✅' if ok else '❌'}" if v is not None else "—"
        lines.append(
            f"| {r.case_id:<10} "
            f"| {_fmt(ce.actual_extraction_confidence, ce.overall_confidence_ok)} "
            f"| {_fmt(ce.actual_seniority_confidence, ce.seniority_confidence_ok)} "
            f"| {_fmt(ce.actual_experience_confidence, ce.experience_confidence_ok)} "
            f"| {_fmt(ce.actual_skills_confidence, ce.skills_confidence_ok)} "
            f"| {'✅' if ce.seniority_correct else ('❌' if ce.seniority_correct is False else '—')} {ce.actual_seniority or ''} "
            f"| {'✅' if ce.years_in_range else ('❌' if ce.years_in_range is False else '—')} {ce.actual_total_years or ''} "
            f"| {ce.contract_score:.0%} |"
        )

    lines += [
        "",
        "## Resultado de Veredito por Caso",
        "",
        "| ID         | Esperado              | Obtido                | Score | Range   | ✓V | ✓S | ✓B | ⏱    |",
        "|------------|-----------------------|-----------------------|-------|---------|----|----|-----|------|",
    ]
    for r in report.per_case:
        if r.error:
            lines.append(f"| {r.case_id:<10} | {r.expected_verdict:<21} | ❌ {r.error[:35]} | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {r.case_id:<10} | {r.expected_verdict:<21} | {(r.actual_verdict or '?'):<21} "
            f"| {(r.actual_score or 0):.1f}{'⚡' if r.cache_hit else ' ':1} "
            f"| [{r.expected_score_min:.0f}–{r.expected_score_max:.0f}] "
            f"| {'✅' if r.verdict_correct else '❌'} "
            f"| {'✅' if r.score_in_range  else '❌'} "
            f"| {'✅' if r.blocker_correct else '❌'} "
            f"| {r.elapsed_sec:.1f}s |"
        )

    # Warnings do contrato
    contract_warnings = [
        (r.case_id, w)
        for r in report.per_case if r.contract_eval
        for w in r.contract_eval.warnings
    ]
    if contract_warnings:
        lines += ["", "## Avisos do Contrato de Confiança", ""]
        for case_id, w in contract_warnings:
            lines.append(f"- **{case_id}**: {w}")

    lines += ["", "---", f"*CV Conformity Agent — Quality Evaluation — {report.run_at}*"]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Terminal
# ─────────────────────────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36", "bold": "1", "dim": "2"}
    return f"\033[{codes.get(code,'0')}m{text}\033[0m"

def _bar_str(v: float, w: int = 15) -> str:
    filled = int(round(v * w))
    return "█" * filled + "░" * (w - filled)


def print_summary(report: EvaluationReport):
    q     = report.overall_quality
    color = "green" if q >= 80 else ("yellow" if q >= 60 else "red")
    print()
    print(_c("bold", "═" * 65))
    print(_c("bold", "  RELATÓRIO DE QUALIDADE — CV Conformity Agent"))
    print(_c("bold", "═" * 65))
    print(f"  Overall Quality Score   : {_c(color, f'{q:.1f} / 100')}")
    print()
    print(_c("bold", "  Métricas de Output (veredito final):"))
    print(f"    Acurácia de Veredito  : {report.verdict_accuracy:.1%}  {_bar_str(report.verdict_accuracy)}")
    print(f"    Calibração de Score   : {report.score_calibration:.1%}  {_bar_str(report.score_calibration)}")
    print(f"    F1 Médio de Skills    : {report.avg_skill_f1:.1%}  {_bar_str(report.avg_skill_f1)}")
    print(f"    Acurácia de Blocker   : {report.blocker_accuracy:.1%}  {_bar_str(report.blocker_accuracy)}")
    print()
    print(_c("bold", "  Contrato de Confiança (qualidade de extração):"))
    print(f"    Contract Score Médio  : {report.avg_contract_score:.1%}  {_bar_str(report.avg_contract_score)}")
    print(f"    Contratos 100% OK     : {report.contract_confidence_rate:.1%}  {_bar_str(report.contract_confidence_rate)}")
    print(f"    Acurácia Senioridade  : {report.seniority_accuracy:.1%}  {_bar_str(report.seniority_accuracy)}")
    print(f"    Acurácia Anos Exp.    : {report.years_accuracy:.1%}  {_bar_str(report.years_accuracy)}")
    print()
    print(_c("bold", "  Por Dimensão:"))
    for dim, m in report.per_dimension.items():
        if not any(m.values()):
            continue
        print(
            f"    {dim:<14}  P={m['precision']:.1%}  R={m['recall']:.1%}  "
            f"F1={m['f1']:.1%}  AvgConf={m['avg_confidence']:.1%}"
        )
    print(f"\n  Casos: {report.executed}/{report.total_cases} executados"
          + (f"  {_c('red', str(report.errors) + ' erros')}" if report.errors else ""))
    print(_c("bold", "═" * 65))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Avalia qualidade do CV Conformity Agent")
    p.add_argument("--cases",         default=None, help="IDs separados por vírgula")
    p.add_argument("--output",        default=None, help="Caminho do relatório Markdown")
    p.add_argument("--json",          action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--dry-run",       action="store_true")
    p.add_argument("--contract-only", action="store_true", help="Foca nas métricas de extração")
    args = p.parse_args()

    all_cases = load_cases()
    if not all_cases:
        print(_c("red", f"Nenhum caso em {RESULTS_FILE}"))
        sys.exit(1)

    if args.cases:
        ids   = {i.strip() for i in args.cases.split(",")}
        cases = [c for c in all_cases if c.id in ids]
    else:
        cases = all_cases

    print(_c("bold", f"\n🔍 CV Conformity Agent — Quality Evaluation ({len(cases)} casos)\n"))

    if args.dry_run:
        all_ok = True
        for case in cases:
            errs = case.validate()
            if errs:
                for e in errs:
                    print(_c("red", f"  ✗ {e}"))
                all_ok = False
            else:
                has_contract = "📋" if case.extraction_contract else "  "
                print(_c("green", f"  ✓ {case.id}") + f"  {has_contract} {case.cv_filename}")
        sys.exit(0 if all_ok else 1)

    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.id} — {case.cv_filename}...", end="", flush=True)
        result = evaluate_case(case)
        results.append(result)
        if result.error:
            print(_c("red", f" ❌ {result.error}"))
        else:
            v_icon = "✅" if result.verdict_correct else "❌"
            cs = f"  📋{result.contract_eval.contract_score:.0%}" if result.contract_eval else ""
            print(
                f" {v_icon} {result.actual_verdict}  "
                f"score={result.actual_score:.1f}  "
                f"⏱{result.elapsed_sec:.1f}s"
                f"{cs}"
                + (" ⚡" if result.cache_hit else "")
            )

    report = aggregate_metrics(results, cases)
    print_summary(report)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = Path(args.output) if args.output else REPORTS_DIR / f"report_{ts}.md"
    md_path.write_text(generate_markdown(report), encoding="utf-8")
    print(f"  📄 Markdown → {md_path}")

    if args.json:
        json_path = md_path.with_suffix(".json")
        json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  📊 JSON    → {json_path}")

    print()
    sys.exit(0 if report.errors == 0 else 1)


if __name__ == "__main__":
    main()
