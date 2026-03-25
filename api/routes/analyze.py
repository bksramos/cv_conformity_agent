from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from loguru import logger

from agents.orchestrator import CVConformityOrchestrator
from api.dependencies import get_orchestrator
from api.schemas import ConformityResultOut, BatchResultOut, DimensionsOut, DimensionScoreOut

router = APIRouter(tags=["Analysis"])


def _dims_to_out(dims) -> DimensionsOut | None:
    if not dims:
        logger.warning("[analyze] _dims_to_out recebeu dims=None — retornando None")
        return None

    def _d(dim, name: str) -> DimensionScoreOut:
        if dim is None:
            logger.warning(
                f"[analyze] Dimensão '{name}' é None — retornando DimensionScoreOut zerado"
            )
            return DimensionScoreOut(
                score=0, weight=0, matched=[], missing=[],
                partial=[], notes=[], is_blocked=False,
            )
        try:
            return DimensionScoreOut(
                score=dim.score, weight=dim.weight,
                matched=dim.matched, missing=dim.missing,
                partial=dim.partial, notes=dim.notes,
                is_blocked=dim.is_blocked,
            )
        except AttributeError as e:
            logger.error(
                f"[analyze] ❌ AttributeError na dimensão '{name}': {e} | "
                f"dim type={type(dim)} | attrs={dir(dim)}"
            )
            return DimensionScoreOut(
                score=0, weight=0, matched=[], missing=[],
                partial=[], notes=[], is_blocked=False,
            )

    return DimensionsOut(
        hard_skills=_d(dims.hard_skills, "hard_skills"),
        experience =_d(dims.experience,  "experience"),
        education  =_d(dims.education,   "education"),
        languages  =_d(dims.languages,   "languages"),
        soft_skills=_d(dims.soft_skills, "soft_skills"),
    )


def _result_to_out(state, cache_hit=False) -> ConformityResultOut:
    r = state.conformity_result
    dims_out = _dims_to_out(r.dimensions)
    logger.debug(
        f"[analyze] _result_to_out | "
        f"candidato='{r.candidate_name}' | score={r.overall_score} | "
        f"veredito={r.verdict.value} | dims_out={'ok' if dims_out else 'None'}"
    )
    return ConformityResultOut(
        id                  = r.id,
        candidate_name      = r.candidate_name,
        jd_title            = r.jd_title,
        verdict             = r.verdict.value,
        overall_score       = r.overall_score,
        has_absolute_blocker= r.has_absolute_blocker,
        dimensions          = dims_out,
        critical_gaps       = r.critical_gaps,
        strengths           = r.strengths,
        partial_matches     = r.partial_matches,
        parecer_final_pt    = r.parecer_final_pt,
        parecer_final_en    = r.parecer_final_en,
        analyzed_at         = r.analyzed_at,
        cache_hit           = state.cache_hit,
    )


@router.post("/analyze", response_model=ConformityResultOut, summary="Análise 1 CV × 1 JD")
async def analyze_one(
    pdf:      UploadFile = File(..., description="PDF do currículo"),
    jd_id:    str | None = Form(None, description="UUID da JD no banco"),
    jd_text:  str | None = Form(None, description="Texto da JD"),
    orchestrator: CVConformityOrchestrator = Depends(get_orchestrator),
):
    if not jd_id and not jd_text:
        raise HTTPException(status_code=422, detail="Informe jd_id ou jd_text")
    if pdf.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Arquivo deve ser um PDF")

    pdf_bytes = await pdf.read()
    jd_uuid   = UUID(jd_id) if jd_id else None

    logger.info(
        f"[analyze] POST /analyze | "
        f"pdf='{pdf.filename}' size={len(pdf_bytes)} bytes | "
        f"jd_id={jd_id} | jd_text={'sim' if jd_text else 'não'}"
    )

    state = await orchestrator.analyze(
        pdf_bytes=pdf_bytes,
        jd_id=jd_uuid,
        jd_input=jd_text,
    )

    if state.errors:
        logger.error(f"[analyze] ❌ Erros no orchestrator: {state.errors}")
        raise HTTPException(status_code=500, detail=state.errors)
    if not state.conformity_result:
        logger.error("[analyze] ❌ conformity_result é None após orchestrator.analyze")
        raise HTTPException(status_code=500, detail="Falha no processamento")

    return _result_to_out(state)


@router.post("/analyze/batch", response_model=BatchResultOut, summary="1 CV × N JDs do banco")
async def analyze_batch(
    pdf:       UploadFile = File(..., description="PDF do currículo"),
    top_k:     int        = Form(10,   description="Quantas vagas analisar"),
    domain:    str | None = Form(None, description="Filtro de domínio: TECH, DATA..."),
    seniority: str | None = Form(None, description="Filtro de senioridade: SENIOR, PLENO..."),
    orchestrator: CVConformityOrchestrator = Depends(get_orchestrator),
):
    if pdf.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Arquivo deve ser um PDF")

    pdf_bytes = await pdf.read()

    logger.info(
        f"[analyze] POST /analyze/batch | "
        f"pdf='{pdf.filename}' size={len(pdf_bytes)} bytes | "
        f"top_k={top_k} | domain={domain} | seniority={seniority}"
    )

    results = await orchestrator.batch_match(
        pdf_bytes=pdf_bytes,
        top_k=top_k,
        domain=domain,
        seniority=seniority,
    )

    if not results:
        logger.warning("[analyze] batch_match retornou lista vazia")
        raise HTTPException(status_code=404, detail="Nenhuma vaga encontrada no banco")

    candidate = results[0].conformity_result.candidate_name if results else "Candidato"
    logger.info(f"[analyze] Batch concluído | candidato='{candidate}' | vagas={len(results)}")

    return BatchResultOut(
        candidate_name  = candidate,
        total_analyzed  = len(results),
        results         = [_result_to_out(s) for s in results],
    )
