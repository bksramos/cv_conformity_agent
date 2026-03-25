# ============================================================
# Testa a extração de um CV em PDF manualmente.
# Uso: python run_cv_extraction.py caminho/para/curriculo.pdf
# ============================================================
import asyncio
import argparse
import json
import sys
from pathlib import Path
from loguru import logger


async def main(pdf_path: str):
    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"Arquivo não encontrado: {pdf_path}")
        sys.exit(1)
    if path.suffix.lower() != ".pdf":
        logger.error("Arquivo deve ser um PDF")
        sys.exit(1)

    from agents.cv_extraction_agent import CVExtractionAgent

    logger.info(f"📄 Extraindo CV: {path.name}")
    pdf_bytes = path.read_bytes()

    async with CVExtractionAgent() as agent:
        profile = await agent.extract_from_bytes(pdf_bytes)

    # Exibe resultado formatado
    logger.info("\n" + "=" * 55)
    logger.info(f"👤 Candidato     : {profile.candidate_name}")
    logger.info(f"📧 Email         : {profile.email}")
    logger.info(f"📍 Localização   : {profile.location}")
    logger.info(f"🎯 Senioridade   : {profile.seniority_inferred.value}")
    logger.info(f"⏱  Experiência   : {profile.total_experience_years} anos")
    logger.info(f"🔧 Hard Skills   : {len(profile.hard_skills)}")

    if profile.hard_skills:
        skills_str = ", ".join(s.name for s in profile.hard_skills[:10])
        logger.info(f"   → {skills_str}")

    logger.info(f"🎓 Formação      : {len(profile.education)}")
    logger.info(f"🌐 Idiomas       : {len(profile.languages)}")
    logger.info(f"💼 Experiências  : {len(profile.experiences)}")
    logger.info(f"📊 Confiança     : {profile.extraction_confidence:.0%}")
    logger.info(f"🔄 Estratégia    : {profile.extraction_strategy}")

    if profile.extraction_warnings:
        logger.warning(f"⚠️  Avisos: {profile.extraction_warnings}")

    logger.info("=" * 55)

    # Salva JSON completo
    output_path = path.with_suffix(".extracted.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    logger.info(f"\n💾 JSON completo salvo em: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrai informações de um currículo PDF.")
    parser.add_argument("pdf", type=str, help="Caminho para o arquivo PDF do currículo")
    args = parser.parse_args()
    asyncio.run(main(args.pdf))
