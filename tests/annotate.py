#!/usr/bin/env python3
# ============================================================
# FILE: tests/annotate.py
# CLI interativa para criar/editar casos de Ground Truth — Fase 6
#
# Uso:
#   python tests/annotate.py                   # cria novo caso
#   python tests/annotate.py --edit case_001   # edita caso existente
#   python tests/annotate.py --list            # lista todos os casos
#   python tests/annotate.py --delete case_001
#   python tests/annotate.py --show case_001   # exibe JSON completo
# ============================================================
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.ground_truth.gt_models import (
    ANNOTATIONS_DIR,
    CVS_DIR,
    DIMENSIONS,
    JDS_DIR,
    RESULTS_FILE,
    DimensionAnnotation,
    ExtractionContractExpectation,
    GroundTruthCase,
    SkillExpectation,
    add_or_replace_case,
    load_cases,
    save_cases,
)

# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36",
             "blue": "34", "bold": "1", "dim": "2"}
    return f"\033[{codes.get(code,'0')}m{text}\033[0m"


def _header(title: str):
    print()
    print(_c("bold", f"  ┌─ {title} {'─' * max(0, 52 - len(title))}┐"))
    print()


def _sep():
    print(_c("dim", "  " + "─" * 58))


def ask(prompt: str, default: str = "", required: bool = False) -> str:
    hint = f" [{_c('dim', default)}]" if default else ""
    while True:
        val = input(f"  {prompt}{hint}: ").strip()
        if not val and default:
            return default
        if not val and required:
            print(_c("red", "    ✗ Campo obrigatório."))
            continue
        return val


def ask_choice(prompt: str, options: list[str], default: str = "") -> str:
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        marker = _c("cyan", "▶") if opt == default else " "
        print(f"  {marker} {i}. {opt}")
    hint = f" [default: {default}]" if default else ""
    while True:
        raw = input(f"  Opção{hint}: ").strip()
        if not raw and default:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw in options:
            return raw
        print(_c("red", f"    ✗ Inválido. Escolha 1–{len(options)}."))


def ask_float(prompt: str, default: float, lo: float = 0, hi: float = 100) -> float:
    while True:
        raw = ask(prompt, default=str(default))
        try:
            v = float(raw)
            if lo <= v <= hi:
                return v
            print(_c("red", f"    ✗ Valor entre {lo} e {hi}."))
        except ValueError:
            print(_c("red", "    ✗ Número inválido."))


def ask_list(prompt: str, hint: str = "") -> list[str]:
    raw = ask(f"{prompt} (vírgula){' — ' + hint if hint else ''}", default="")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []


# ─────────────────────────────────────────────────────────────────────────────
# Seleção de arquivos
# ─────────────────────────────────────────────────────────────────────────────

def _pick_file(directory: Path, ext: str, label: str) -> str:
    files = sorted(p.name for p in directory.glob(f"*.{ext}")) if directory.exists() else []
    if not files:
        print(_c("yellow", f"  ⚠ Nenhum .{ext} em {directory}"))
        directory.mkdir(parents=True, exist_ok=True)
        return ask(f"Nome do arquivo .{ext}", required=True)
    return ask_choice(f"Selecione o {label}", files)


# ─────────────────────────────────────────────────────────────────────────────
# Anotação de skills com confiança
# ─────────────────────────────────────────────────────────────────────────────

def _ask_skill_expectations(
    prompt: str,
    existing: list[SkillExpectation],
) -> list[SkillExpectation]:
    """
    Coleta skills com threshold de confiança individual.
    Formato de entrada: "Python:0.9, FastAPI, Docker:0.7"
    Sem sufixo = min_confidence padrão de 0.7
    """
    existing_str = ", ".join(
        f"{s.name}:{s.min_confidence}" for s in existing
    ) if existing else ""

    print(f"\n  {prompt}")
    print(_c("dim", "  Formato: NomeDaSkill:confiança_mínima (ex: Python:0.9, FastAPI, Docker:0.7)"))
    print(_c("dim", "  Sem sufixo = confiança padrão 0.7. Enter para manter atual."))
    raw = ask("  Skills", default=existing_str)

    if not raw:
        return existing

    result = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, conf_str = part.rsplit(":", 1)
            try:
                conf = max(0.0, min(1.0, float(conf_str)))
            except ValueError:
                conf = 0.7
            result.append(SkillExpectation(name=name.strip(), min_confidence=conf))
        else:
            result.append(SkillExpectation(name=part, min_confidence=0.7))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Anotação por dimensão
# ─────────────────────────────────────────────────────────────────────────────

def _annotate_dimension(dim_key: str, existing: Optional[DimensionAnnotation]) -> DimensionAnnotation:
    ex = existing or DimensionAnnotation()
    print(f"\n  {_c('cyan', f'── Dimensão: {dim_key}')}")

    skills_present = _ask_skill_expectations(
        "Skills/itens que devem ser encontrados (com confiança mínima):",
        ex.expected_skills_present,
    )

    absent_raw = ask_list(
        "  Skills/itens que devem estar AUSENTES",
        hint=", ".join(ex.expected_skills_absent) or "ex: Kubernetes",
    ) or ex.expected_skills_absent

    print(f"\n  Score esperado para '{dim_key}':")
    score_min = ask_float("    Mínimo", default=ex.expected_score_min)
    score_max = ask_float("    Máximo", default=ex.expected_score_max)

    print(f"\n  Confiança mínima esperada para esta dimensão (0.0–1.0):")
    min_conf = ask_float("    Threshold", default=ex.min_dimension_confidence, lo=0.0, hi=1.0)

    notes = ask("  Observações", default=ex.notes)

    return DimensionAnnotation(
        expected_skills_present  = skills_present,
        expected_skills_absent   = absent_raw,
        expected_score_min       = score_min,
        expected_score_max       = score_max,
        min_dimension_confidence = min_conf,
        notes                    = notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Contrato de confiança
# ─────────────────────────────────────────────────────────────────────────────

def _ask_extraction_contract(
    existing: Optional[ExtractionContractExpectation],
) -> Optional[ExtractionContractExpectation]:
    ex = existing or ExtractionContractExpectation()

    add = ask_choice(
        "Definir contrato de confiança de extração (CVProfile)?",
        ["Sim", "Pular"],
        default="Sim" if existing else "Pular",
    )
    if add == "Pular":
        return None

    print(_c("dim", "\n  Thresholds mínimos que a extração do CVProfile deve atingir:\n"))

    min_ext  = ask_float("  Min extraction_confidence", default=ex.min_extraction_confidence, lo=0.0, hi=1.0)
    min_sen  = ask_float("  Min seniority_confidence",  default=ex.min_seniority_confidence,  lo=0.0, hi=1.0)
    min_exp  = ask_float("  Min experience_confidence", default=ex.min_experience_confidence, lo=0.0, hi=1.0)
    min_ski  = ask_float("  Min skills_confidence",     default=ex.min_skills_confidence,     lo=0.0, hi=1.0)

    print(_c("dim", "\n  Valores esperados (deixe em branco para não validar):"))

    seniority_options = [
        "ESTAGIO", "JUNIOR", "PLENO", "SENIOR",
        "ESPECIALISTA", "LIDERANCA", "NAO_INFORMADO", "(pular)",
    ]
    sen_choice = ask_choice(
        "Senioridade esperada no CVProfile:",
        seniority_options,
        default=ex.expected_seniority or "(pular)",
    )
    expected_seniority = None if sen_choice == "(pular)" else sen_choice

    years_min_raw = ask("  Anos de experiência — mínimo esperado", default=str(ex.expected_total_years_min or ""))
    years_max_raw = ask("  Anos de experiência — máximo esperado", default=str(ex.expected_total_years_max or ""))

    try:    years_min: Optional[float] = float(years_min_raw) if years_min_raw else None
    except: years_min = None
    try:    years_max: Optional[float] = float(years_max_raw) if years_max_raw else None
    except: years_max = None

    source_options = ["cross_validated", "years_only", "title_only",
                      "title_overrides_years", "years_overrides_title", "(pular)"]
    src_choice = ask_choice(
        "Source de senioridade esperado:",
        source_options,
        default=ex.expected_seniority_source or "(pular)",
    )
    expected_source = None if src_choice == "(pular)" else src_choice

    notes = ask("  Observações do contrato", default=ex.notes)

    return ExtractionContractExpectation(
        min_extraction_confidence = min_ext,
        min_seniority_confidence  = min_sen,
        min_experience_confidence = min_exp,
        min_skills_confidence     = min_ski,
        expected_seniority        = expected_seniority,
        expected_total_years_min  = years_min,
        expected_total_years_max  = years_max,
        expected_seniority_source = expected_source,
        notes                     = notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Builder principal do caso
# ─────────────────────────────────────────────────────────────────────────────

def _build_case(existing: Optional[GroundTruthCase] = None) -> GroundTruthCase:
    ex = existing

    _header("Identificação do Caso")
    default_id = ex.id if ex else f"case_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    case_id    = ask("ID do caso", default=default_id, required=True)

    print()
    cv_filename = _pick_file(CVS_DIR, "pdf", "currículo (PDF)")

    _header("Fonte da Job Description")
    jd_source = ask_choice("Origem da JD:", ["file", "db"], default=ex.jd_source if ex else "file")
    jd_filename, jd_id = None, None
    if jd_source == "file":
        jd_filename = _pick_file(JDS_DIR, "json", "JD (JSON)")
    else:
        jd_id = ask("UUID da JD no banco", default=ex.jd_id or "", required=True)

    _header("Resultado Esperado")
    expected_verdict = ask_choice(
        "Veredito esperado:",
        ["APROVADO", "APROVADO_COM_RESSALVAS", "REPROVADO"],
        default=ex.expected_verdict if ex else "APROVADO",
    )
    print("\n  Faixa de score esperada:")
    score_min = ask_float("    Mínimo", default=ex.expected_score_min if ex else 50.0)
    score_max = ask_float("    Máximo", default=ex.expected_score_max if ex else 80.0)
    if score_min > score_max:
        score_min, score_max = score_max, score_min

    blocker_raw = ask_choice(
        "Bloqueador absoluto esperado?",
        ["Não", "Sim"],
        default="Sim" if (ex and ex.expected_absolute_blocker) else "Não",
    )

    # Anotações por dimensão
    _header("Anotações por Dimensão")
    print(_c("dim", "  Defina skills esperadas com threshold de confiança por dimensão."))
    annotations: dict[str, DimensionAnnotation] = {}
    for dim_key in DIMENSIONS:
        skip = ask_choice(
            f"\n  Anotar '{dim_key}'?",
            ["Sim", "Pular"],
            default="Sim" if (ex and dim_key in ex.annotations) else "Pular",
        )
        if skip == "Sim":
            annotations[dim_key] = _annotate_dimension(dim_key, ex.annotations.get(dim_key) if ex else None)

    # Contrato de confiança
    _header("Contrato de Confiança da Extração")
    extraction_contract = _ask_extraction_contract(ex.extraction_contract if ex else None)

    _header("Metadados")
    notes        = ask("Observações gerais", default=ex.notes if ex else "")
    annotated_by = ask("Anotado por", default=ex.annotated_by if ex else os.getenv("USER", "brunno"))

    return GroundTruthCase(
        id                        = case_id,
        cv_filename               = cv_filename,
        jd_source                 = jd_source,
        jd_filename               = jd_filename,
        jd_id                     = jd_id,
        expected_verdict          = expected_verdict,
        expected_score_min        = score_min,
        expected_score_max        = score_max,
        expected_absolute_blocker = blocker_raw == "Sim",
        annotations               = annotations,
        extraction_contract       = extraction_contract,
        notes                     = notes,
        annotated_by              = annotated_by,
        annotated_at              = datetime.now().isoformat(timespec="seconds"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Comandos
# ─────────────────────────────────────────────────────────────────────────────

def cmd_create():
    print(_c("bold", "\n  ✏️  Criar novo caso de Ground Truth"))
    case = _build_case()

    _sep()
    print(_c("bold", "\n  Resumo:"))
    print(f"  ID:              {case.id}")
    print(f"  CV:              {case.cv_filename}")
    print(f"  Veredito:        {case.expected_verdict}  [{case.expected_score_min}–{case.expected_score_max}]")
    print(f"  Blocker:         {case.expected_absolute_blocker}")
    print(f"  Dims anotadas:   {list(case.annotations.keys()) or '(nenhuma)'}")
    print(f"  Contrato:        {'Sim' if case.extraction_contract else 'Não'}")
    _sep()

    confirm = ask_choice("Salvar?", ["Sim", "Cancelar"], default="Sim")
    if confirm == "Cancelar":
        print(_c("yellow", "\n  Cancelado."))
        return

    errs = case.validate()
    if errs:
        print(_c("red", "\n  ⚠ Avisos:"))
        for e in errs:
            print(_c("yellow", f"    - {e}"))
        if ask_choice("Salvar mesmo assim?", ["Sim", "Cancelar"], default="Cancelar") == "Cancelar":
            return

    add_or_replace_case(case)
    print(_c("green", f"\n  ✅ Caso '{case.id}' salvo.\n"))


def cmd_edit(case_id: str):
    existing = next((c for c in load_cases() if c.id == case_id), None)
    if not existing:
        print(_c("red", f"\n  Caso '{case_id}' não encontrado."))
        sys.exit(1)
    print(_c("bold", f"\n  ✏️  Editando: {case_id}"))
    case = _build_case(existing=existing)
    add_or_replace_case(case)
    print(_c("green", f"\n  ✅ Caso '{case.id}' atualizado.\n"))


def cmd_list():
    cases = load_cases()
    if not cases:
        print(_c("yellow", "\n  Nenhum caso encontrado.\n"))
        return
    print(_c("bold", f"\n  Ground Truth — {len(cases)} caso(s)\n"))
    print(f"  {'ID':<20} {'CV':<32} {'Veredito':<25} {'Range':<10} {'Contrato':<8} {'Por'}")
    print("  " + "─" * 105)
    for c in cases:
        contract_icon = "📋" if c.extraction_contract else "  "
        print(
            f"  {c.id:<20} {c.cv_filename[:31]:<32} {c.expected_verdict:<25} "
            f"[{c.expected_score_min:.0f}–{c.expected_score_max:.0f}]{'':3} "
            f"{contract_icon}{'':6} {c.annotated_by}"
        )
    print()


def cmd_delete(case_id: str):
    cases = load_cases()
    original = len(cases)
    cases = [c for c in cases if c.id != case_id]
    if len(cases) == original:
        print(_c("red", f"\n  Caso '{case_id}' não encontrado."))
        sys.exit(1)
    if ask_choice(f"Excluir '{case_id}'?", ["Sim, excluir", "Cancelar"], default="Cancelar") != "Sim, excluir":
        print(_c("yellow", "\n  Cancelado."))
        return
    save_cases(cases)
    print(_c("green", f"\n  ✅ Caso '{case_id}' removido.\n"))


def cmd_show(case_id: str):
    case = next((c for c in load_cases() if c.id == case_id), None)
    if not case:
        print(_c("red", f"\n  Caso '{case_id}' não encontrado."))
        sys.exit(1)
    print(json.dumps(case.to_dict(), ensure_ascii=False, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Gerencia casos de Ground Truth")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--list",   "-l", action="store_true")
    g.add_argument("--edit",   "-e", metavar="ID")
    g.add_argument("--delete", "-d", metavar="ID")
    g.add_argument("--show",   "-s", metavar="ID")
    args = p.parse_args()

    if args.list:     cmd_list()
    elif args.edit:   cmd_edit(args.edit)
    elif args.delete: cmd_delete(args.delete)
    elif args.show:   cmd_show(args.show)
    else:             cmd_create()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(_c("yellow", "\n\n  Interrompido.\n"))
        sys.exit(0)