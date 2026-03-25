# ============================================================
# Roda a análise completa: PDF + JD → Parecer
# Uso:
#   python run_analysis.py curriculo.pdf --jd-id <uuid>
#   python run_analysis.py curriculo.pdf --jd-text "texto da vaga"
# ============================================================
import asyncio
import argparse
import sys
from pathlib import Path
from loguru import logger


async def main(pdf_path: str, jd_id: str | None, jd_text: str | None):
    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"Arquivo não encontrado: {pdf_path}")
        sys.exit(1)

    from agents.cv_extraction_agent import CVExtractionAgent
    from agents.jd_extraction_agent import JDExtractionAgent
    from agents.conformity_validator import ConformityValidator
    from agents.report_generator import ReportGenerator
    from scraper.base_scraper import RawJob
    from datetime import datetime

    pdf_bytes = path.read_bytes()

    # --- 1. Extrai CV ---
    logger.info("📄 Extraindo CV...")
    async with CVExtractionAgent() as cv_agent:
        cv = await cv_agent.extract_from_bytes(pdf_bytes)
    logger.info(f"   → {cv.candidate_name} | {cv.total_experience_years}a | {cv.seniority_inferred.value}")

    # --- 2. Obtém JD ---
    if jd_id:
        from database.connection import AsyncSessionLocal
        from database.repositories.jd_repository import JDRepository
        from models.jd_model import JobDescription
        import uuid
        async with AsyncSessionLocal() as session:
            repo = JDRepository(session)
            orm  = await repo.get_by_id(uuid.UUID(jd_id))
            if not orm or not orm.structured_data:
                logger.error(f"JD {jd_id} não encontrada")
                sys.exit(1)
            jd = JobDescription(**orm.structured_data)
    elif jd_text:
        logger.info("📋 Extraindo JD do texto...")
        raw_job = RawJob(
            source="manual", source_url="manual://input",
            title="Vaga Manual", company="",
            raw_text=jd_text, scraped_at=datetime.utcnow(),
        )
        async with JDExtractionAgent() as jd_agent:
            jd = await jd_agent.extract(raw_job)
        if not jd:
            logger.error("Falha ao extrair JD")
            sys.exit(1)
    else:
        logger.error("Informe --jd-id ou --jd-text")
        sys.exit(1)

    logger.info(f"   → {jd.title} | {jd.seniority.value} | {len(jd.required_skills)} skills")

    # --- 3. Valida conformidade ---
    logger.info("🔍 Validando conformidade...")
    validator = ConformityValidator()
    result    = validator.validate(cv, jd)

    # --- 4. Gera parecer ---
    logger.info("✍️  Gerando parecer...")
    async with ReportGenerator() as reporter:
        result = await reporter.generate(result)

    # --- 5. Exibe resultado ---
    verdict_icon = {"APROVADO": "✅", "APROVADO_COM_RESSALVAS": "⚠️", "REPROVADO": "❌"}.get(result.verdict.value, "❓")
    logger.info("\n" + "=" * 60)
    logger.info(f"{verdict_icon} VEREDITO : {result.verdict.value}")
    logger.info(f"📊 SCORE   : {result.overall_score}/100")
    logger.info(f"🔧 Skills  : {result.dimensions.hard_skills.score}/100{'  ⛔ BLOQUEADOR' if result.has_absolute_blocker else ''}")
    logger.info(f"⏱  Exp     : {result.dimensions.experience.score}/100")
    logger.info(f"🎓 Formação: {result.dimensions.education.score}/100")
    logger.info(f"🌐 Idiomas : {result.dimensions.languages.score}/100")

    if result.critical_gaps:
        logger.info(f"\n⛔ Lacunas críticas:")
        for g in result.critical_gaps:
            logger.info(f"   • {g}")

    if result.strengths:
        logger.info(f"\n💪 Pontos fortes:")
        for s in result.strengths[:5]:
            logger.info(f"   • {s}")

    logger.info(f"\n📝 PARECER PT:\n{result.parecer_final_pt}")
    logger.info(f"\n📝 PARECER EN:\n{result.parecer_final_en}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="Caminho para o PDF do currículo")
    parser.add_argument("--jd-id",   help="UUID da JD no banco de dados")
    parser.add_argument("--jd-text", help="Texto da JD diretamente")
    args = parser.parse_args()
    asyncio.run(main(args.pdf, args.jd_id, args.jd_text))
