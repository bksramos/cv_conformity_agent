# ============================================================
# FILE: bootstrap.py
# Roda uma vez para validar que todo o ambiente está OK.
# Execute: python bootstrap.py
# ============================================================
import asyncio
import sys
import httpx
from loguru import logger

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | {level} | {message}", level="DEBUG")


async def check_postgres():
    from database.connection import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.success("✅ PostgreSQL — OK")
        return True
    except Exception as e:
        logger.error(f"❌ PostgreSQL — FALHOU: {e}")
        return False


async def check_ollama():
    from config.settings import settings
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            if settings.ollama_model in models:
                logger.success(f"✅ Ollama — OK ({settings.ollama_model} disponível)")
            else:
                logger.warning(
                    f"⚠️  Ollama — rodando mas '{settings.ollama_model}' não encontrado. "
                    f"Modelos disponíveis: {models}. Execute: ollama pull {settings.ollama_model}"
                )
        return True
    except Exception as e:
        logger.error(f"❌ Ollama — FALHOU: {e}")
        return False


async def check_redis():
    import redis.asyncio as aioredis
    from config.settings import settings
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        logger.success("✅ Redis — OK")
        return True
    except Exception as e:
        logger.error(f"❌ Redis — FALHOU: {e}")
        return False


async def check_chromadb():
    from config.settings import settings
    # ChromaDB mudou endpoints entre versões — testa os dois
    base = f"http://{settings.chroma_host}:{settings.chroma_port}"
    candidates = [
        f"{base}/api/v1/heartbeat",   # v0.4.x
        f"{base}/api/v2/heartbeat",   # v0.5.x+
        f"{base}/api/v1",             # algumas builds respondem na raiz da API
        f"{base}/healthz",            # fallback genérico
    ]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for url in candidates:
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        logger.success(f"✅ ChromaDB — OK (endpoint: {url})")
                        return True
                    else:
                        logger.debug(f"   ChromaDB {url} → HTTP {r.status_code}")
                except httpx.ConnectError:
                    logger.debug(f"   ChromaDB {url} → connection refused")

            logger.error(
                f"❌ ChromaDB — nenhum endpoint respondeu 200. "
                f"Verifique se a porta {settings.chroma_port} está correta no .env "
                f"e se o container está saudável: docker compose logs chromadb"
            )
            return False
    except Exception as e:
        logger.error(f"❌ ChromaDB — FALHOU: {type(e).__name__}: {e}")
        return False


async def check_feature_flags():
    from config.feature_flags import flags
    summary = flags.summary()
    active = [k for k, v in summary.items() if v is True]
    logger.info(f"🚩 Feature flags ativas ({len(active)}): {', '.join(active[:5])}...")
    logger.success("✅ Feature Flags — OK")
    return True


async def smoke_test_llm():
    """Envia um prompt simples ao Llama 3 para validar a integração."""
    from config.settings import settings
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            r = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": "Responda apenas: OK",
                    "stream": False
                }
            )
            resp = r.json().get("response", "").strip()
            logger.success(f"✅ Llama 3 smoke test — Resposta: '{resp}'")
            return True
    except Exception as e:
        logger.error(f"❌ Llama 3 smoke test — FALHOU: {e}")
        return False


CHECKS = [
    ("PostgreSQL",    check_postgres),
    ("Ollama",        check_ollama),
    ("Redis",         check_redis),
    ("ChromaDB",      check_chromadb),
    ("Feature Flags", check_feature_flags),
]


async def run_check(name: str, fn) -> bool:
    """Executa um check e garante que qualquer exceção não silenciosa é logada."""
    try:
        result = await fn()
        return result is True
    except Exception as e:
        logger.error(f"❌ {name} — exceção não tratada: {type(e).__name__}: {e}")
        return False


async def main():
    logger.info("=" * 55)
    logger.info(" CV Conformity Agent — Bootstrap & Environment Check")
    logger.info("=" * 55)

    # Roda cada check individualmente para garantir visibilidade total dos erros
    statuses = {}
    for name, fn in CHECKS:
        statuses[name] = await run_check(name, fn)

    # Resumo
    logger.info("\n" + "=" * 55)
    logger.info("📋 Resumo:")
    all_ok = True
    for name, ok in statuses.items():
        icon = "✅" if ok else "❌"
        logger.info(f"   {icon} {name}")
        if not ok:
            all_ok = False

    logger.info("=" * 55)

    if all_ok:
        logger.info("\n🔥 Smoke test do LLM...")
        await smoke_test_llm()
        logger.info("\n" + "=" * 55)
        logger.success("🚀 Ambiente 100% pronto! Próximos passos:")
        logger.info("   1. make api      → FastAPI em http://localhost:8000/docs")
        logger.info("   2. make ui       → Streamlit em http://localhost:8501")
        logger.info("   3. Fase 1: implementar o Gupy scraper")
    else:
        failed = [n for n, ok in statuses.items() if not ok]
        logger.error(f"\n❌ {len(failed)} serviço(s) falharam: {', '.join(failed)}")
        logger.info("\n💡 Dicas de resolução:")
        if "PostgreSQL" in failed:
            logger.info("   • PostgreSQL → execute: docker compose up -d postgres")
        if "Ollama" in failed:
            logger.info("   • Ollama     → verifique se o Ollama está instalado e rodando: ollama serve")
            logger.info("                  depois: ollama pull llama3.1:8b")
        if "Redis" in failed:
            logger.info("   • Redis      → execute: docker compose up -d redis")
        if "ChromaDB" in failed:
            logger.info("   • ChromaDB   → execute: docker compose up -d chromadb")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


# ============================================================
# SCRIPT: create_structure.sh
# Cria todos os diretórios e __init__.py do projeto
# Execute: bash create_structure.sh
# ============================================================
# #!/bin/bash
# set -e
# echo "📁 Criando estrutura do projeto..."
#
# DIRS=(
#   "agents/domain"
#   "scraper/sources"
#   "extractors"
#   "models"
#   "validators"
#   "scoring"
#   "database/repositories"
#   "database/migrations/versions"
#   "cache"
#   "config/prompts"
#   "api/routes"
#   "ui"
#   "tests/ground_truth/cvs"
#   "tests/ground_truth/jds"
#   "uploads"
#   "results"
# )
#
# for dir in "${DIRS[@]}"; do
#   mkdir -p "$dir"
#   touch "$dir/__init__.py" 2>/dev/null || true
# done
#
# # Arquivos raiz
# touch bootstrap.py alembic.ini .env.example .gitignore
#
# # .gitignore básico
# cat > .gitignore << 'EOF'
# .env
# .venv/
# __pycache__/
# *.pyc
# uploads/
# results/
# *.pdf
# chroma_data/
# EOF
#
# echo "✅ Estrutura criada com sucesso!"
# echo ""
# echo "Próximos passos:"
# echo "  1. cp .env.example .env"
# echo "  2. make setup"
# echo "  3. python bootstrap.py"
