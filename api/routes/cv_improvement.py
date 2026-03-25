from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from loguru import logger

from agents.cv_extraction_agent import CVExtractionAgent
from agents.cv_improvement_agent import CVImprovementAgent
from agents.orchestrator import CVConformityOrchestrator
from api.dependencies import get_orchestrator

router = APIRouter(tags=["CV Improvement"])


@router.post("/cv/diagnose", summary="Diagnóstico estrutural do CV (sem LLM de melhoria)")
async def diagnose_cv(
    pdf: UploadFile = File(...),
):
    """
    Extrai o CV e retorna diagnóstico determinístico baseado no contrato de confiança.
    Não chama LLM para melhorias — resultado imediato.
    """
    if pdf.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Arquivo deve ser um PDF")

    pdf_bytes = await pdf.read()
    logger.info(f"[cv/diagnose] '{pdf.filename}' size={len(pdf_bytes)} bytes")

    async with CVExtractionAgent() as extractor:
        profile = await extractor.extract_from_bytes(pdf_bytes)

    agent     = CVImprovementAgent()
    diagnosis = agent.diagnose(profile)

    return {
        "candidate_name":        profile.candidate_name,
        "extraction_confidence": profile.extraction_confidence,
        "diagnosis":             diagnosis.to_dict(),
    }


@router.post("/cv/improve", summary="Diagnóstico + melhoria de clareza via LLM")
async def improve_cv(
    pdf:    UploadFile  = File(...),
    jd_id:  str | None  = Form(None, description="UUID da JD alvo (opcional)"),
    orchestrator: CVConformityOrchestrator = Depends(get_orchestrator),
):
    """
    Extrai o CV, diagnostica e melhora clareza das descrições via LLM.
    Se jd_id for informado, alinha as melhorias com as keywords da vaga.
    """
    if pdf.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Arquivo deve ser um PDF")

    pdf_bytes = await pdf.read()
    logger.info(
        f"[cv/improve] '{pdf.filename}' size={len(pdf_bytes)} bytes | jd_id={jd_id}"
    )

    # Extrai CV
    async with CVExtractionAgent() as extractor:
        profile = await extractor.extract_from_bytes(pdf_bytes)

    # Carrega JD via orchestrator se informada
    jd = None
    if jd_id:
        try:
            # Tenta acessar o repositório de JDs pelo orchestrator
            jd_repo = getattr(orchestrator, "jd_repository", None) \
                   or getattr(orchestrator, "_jd_repository", None) \
                   or getattr(orchestrator, "jd_repo", None)
            if jd_repo:
                jd = await jd_repo.get_by_id(UUID(jd_id))
            if not jd:
                logger.warning(
                    f"[cv/improve] JD {jd_id} não encontrada ou repositório "
                    f"não acessível via orchestrator — prosseguindo sem alvo"
                )
        except Exception as e:
            logger.warning(f"[cv/improve] Erro ao carregar JD: {e} — prosseguindo sem alvo")

    # Diagnóstico + melhoria
    async with CVImprovementAgent() as agent:
        result = await agent.improve_clarity(profile, jd=jd)

    return result.to_dict()