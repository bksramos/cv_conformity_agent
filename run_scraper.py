# ============================================================
# Executa o scraper manualmente, sem precisar da API.
# Uso: python run_scraper.py
#      python run_scraper.py --source gupy
#      python run_scraper.py --source remoteok
# ============================================================
import asyncio
import argparse
import sys
from loguru import logger
from config.feature_flags import flags
from scraper.runner import ScraperRunner, SCRAPER_REGISTRY


async def main(source: str | None, limit: int | None = None):
    if source:
        if source not in SCRAPER_REGISTRY:
            logger.error(f"Source '{source}' inválida. Disponíveis: {list(SCRAPER_REGISTRY.keys())}")
            sys.exit(1)
        # Força apenas o scraper solicitado, ignorando as flags
        original = flags.ENABLED_SCRAPERS
        flags.ENABLED_SCRAPERS = [source]

    runner = ScraperRunner(extraction_limit=limit)
    summary = await runner.run_all()

    logger.info("\n📋 Resumo final:")
    for src, stats in summary.items():
        logger.info(
            f"   {src}: {stats.get('inserted', 0)} inseridas | "
            f"{stats.get('duplicated', 0)} duplicadas | "
            f"{stats.get('failed', 0)} falhas | status={stats.get('status')}"
        )

    if source:
        flags.ENABLED_SCRAPERS = original


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executa o scraper de vagas manualmente.")
    parser.add_argument("--source", type=str, help="Fonte específica (gupy, remoteok)", default=None)
    parser.add_argument("--limit", type=int, help="Limita nº de vagas extraídas via LLM (útil para testes)", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.source, args.limit))