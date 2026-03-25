# ============================================================
# Uso:
#   python run_match.py curriculo.pdf --jd-id <uuid>
#   python run_match.py curriculo.pdf --jd-text "texto da vaga"
# ============================================================
import asyncio
import argparse
import sys
from pathlib import Path
from loguru import logger


async def main(pdf_path: str, jd_id: str | None, jd_text: str | None):
    from cache.validation_cache import ValidationCache
    from cache.embedding_cache import EmbeddingCache
    from agents.orchestrator import CVConformityOrchestrator
    import uuid as _uuid

    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"Arquivo não encontrado: {pdf_path}")
        sys.exit(1)

    pdf_bytes = path.read_bytes()

    # Inicializa caches
    v_cache = ValidationCache()
    e_cache = EmbeddingCache()
    await v_cache.connect()
    await e_cache.connect()

    orchestrator = CVConformityOrchestrator(v_cache, e_cache)

    try:
        state = await orchestrator.analyze(
            pdf_bytes=pdf_bytes,
            jd_id=_uuid.UUID(jd_id) if jd_id else None,
            jd_input=jd_text,
        )
    finally:
        await v_cache.disconnect()

    if state.errors:
        logger.error(f"❌ Erros: {state.errors}")
        sys.exit(1)

    r = state.conformity_result
    verdict_icon = {"APROVADO": "✅", "APROVADO_COM_RESSALVAS": "⚠️", "REPROVADO": "❌"}.get(
        r.verdict.value, "❓"
    )

    logger.info("\n" + "=" * 60)
    logger.info(f"{'[CACHE HIT]' if state.cache_hit else '[PROCESSADO]'}")
    logger.info(f"{verdict_icon}  VEREDITO : {r.verdict.value}")
    logger.info(f"📊 SCORE   : {r.overall_score}/100")
    logger.info(f"🔧 Skills  : {r.dimensions.hard_skills.score}/100"
                + ("  ⛔ BLOQUEADOR" if r.has_absolute_blocker else ""))
    logger.info(f"⏱  Exp     : {r.dimensions.experience.score}/100")
    logger.info(f"🎓 Formação: {r.dimensions.education.score}/100")
    logger.info(f"🌐 Idiomas : {r.dimensions.languages.score}/100")

    if r.critical_gaps:
        logger.info("\n⛔ Lacunas críticas:")
        for g in r.critical_gaps:
            logger.info(f"   • {g}")

    if r.strengths:
        logger.info("\n💪 Pontos fortes:")
        for s in r.strengths[:5]:
            logger.info(f"   • {s}")

    logger.info(f"\n📝 PARECER PT:\n{r.parecer_final_pt}")
    logger.info(f"\n📝 PARECER EN:\n{r.parecer_final_en}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Análise 1 CV × 1 JD")
    parser.add_argument("pdf",       help="Caminho para o PDF do currículo")
    parser.add_argument("--jd-id",   help="UUID da JD no banco")
    parser.add_argument("--jd-text", help="Texto da JD diretamente")
    args = parser.parse_args()
    asyncio.run(main(args.pdf, args.jd_id, args.jd_text))
