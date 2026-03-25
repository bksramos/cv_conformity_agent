# ============================================================
# Uso:
#   python run_batch_match.py curriculo.pdf
#   python run_batch_match.py curriculo.pdf --top 5 --domain TECH
#   python run_batch_match.py curriculo.pdf --top 10 --seniority SENIOR
# ============================================================
import asyncio
import argparse
import sys
from pathlib import Path
from loguru import logger


async def main(pdf_path: str, top_k: int, domain: str | None, seniority: str | None):
    from cache.validation_cache import ValidationCache
    from cache.embedding_cache import EmbeddingCache
    from agents.orchestrator import CVConformityOrchestrator

    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"Arquivo não encontrado: {pdf_path}")
        sys.exit(1)

    pdf_bytes = path.read_bytes()

    v_cache = ValidationCache()
    e_cache = EmbeddingCache()
    await v_cache.connect()
    await e_cache.connect()

    orchestrator = CVConformityOrchestrator(v_cache, e_cache)

    logger.info(f"🔍 Buscando as {top_k} melhores vagas para o candidato...")

    try:
        results = await orchestrator.batch_match(
            pdf_bytes=pdf_bytes,
            top_k=top_k,
            domain=domain,
            seniority=seniority,
        )
    finally:
        await v_cache.disconnect()

    if not results:
        logger.warning("Nenhum resultado encontrado.")
        sys.exit(0)

    candidate_name = results[0].conformity_result.candidate_name if results else "Candidato"

    logger.info(f"\n{'=' * 60}")
    logger.info(f"🏆 RANKING DE VAGAS — {candidate_name}")
    logger.info(f"{'=' * 60}")

    for i, state in enumerate(results, 1):
        r = state.conformity_result
        verdict_icon = {
            "APROVADO":              "✅",
            "APROVADO_COM_RESSALVAS": "⚠️",
            "REPROVADO":             "❌",
        }.get(r.verdict.value, "❓")

        logger.info(
            f"\n#{i:02d} {verdict_icon} [{r.overall_score:5.1f}/100] {r.jd_title}"
            + (" ⛔" if r.has_absolute_blocker else "")
        )
        logger.info(
            f"     Skills={r.dimensions.hard_skills.score:.0f} | "
            f"Exp={r.dimensions.experience.score:.0f} | "
            f"Edu={r.dimensions.education.score:.0f} | "
            f"Lang={r.dimensions.languages.score:.0f}"
        )
        if r.critical_gaps:
            logger.info(f"     ⛔ Gaps: {', '.join(r.critical_gaps[:3])}")
        if r.strengths:
            logger.info(f"     💪 Forças: {', '.join(r.strengths[:3])}")

    logger.info(f"\n{'=' * 60}")
    aprovadas = sum(1 for r in results if r.conformity_result.verdict.value == "APROVADO")
    parciais  = sum(1 for r in results if r.conformity_result.verdict.value == "APROVADO_COM_RESSALVAS")
    reprovadas= sum(1 for r in results if r.conformity_result.verdict.value == "REPROVADO")
    logger.info(
        f"📊 Resumo: {aprovadas} aprovadas | {parciais} com ressalvas | {reprovadas} reprovadas"
    )
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch match: 1 CV × N JDs do banco")
    parser.add_argument("pdf",         help="Caminho para o PDF do currículo")
    parser.add_argument("--top",       type=int, default=10,  help="Quantas vagas analisar (default: 10)")
    parser.add_argument("--domain",    type=str, default=None, help="Filtrar por domínio: TECH, DATA, etc.")
    parser.add_argument("--seniority", type=str, default=None, help="Filtrar por senioridade: SENIOR, PLENO, etc.")
    args = parser.parse_args()
    asyncio.run(main(args.pdf, args.top, args.domain, args.seniority))
