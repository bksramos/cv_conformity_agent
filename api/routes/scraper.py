# ============================================================
# Disparo manual do scraper via API + gestão de vagas arquivadas
# ============================================================
from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException
from loguru import logger
from pydantic import BaseModel

router = APIRouter(tags=["Scraper"])

# ── Estado do scraper (in-memory — single instance) ──────────────────────────

class ScraperStatus(BaseModel):
    running:    bool = False
    last_run:   str | None = None
    last_error: str | None = None
    last_result: str | None = None

_status = ScraperStatus()

# Caminho do script na raiz do projeto
_SCRAPER_SCRIPT = Path(__file__).parent.parent.parent / "run_scraper.py"


# ── Background task ───────────────────────────────────────────────────────────

async def _run_single(source: str) -> tuple[bool, str]:
    """Roda o scraper para uma fonte. Retorna (sucesso, output/erro)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(_SCRAPER_SCRIPT),
        "--source", source,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        out = stdout.decode("utf-8", errors="replace").strip()
        return True, out[-500:] if len(out) > 500 else out
    else:
        err = stderr.decode("utf-8", errors="replace").strip()
        return False, err[-500:] if len(err) > 500 else err


async def _run_scraper_task(source: str):
    global _status
    _status.running     = True
    _status.last_error  = None
    _status.last_result = None
    logger.info(f"[Scraper] Iniciando | source={source}")

    try:
        sources = ["gupy", "remoteok"] if source == "all" else [source]
        results, errors = [], []

        for src in sources:
            logger.info(f"[Scraper] Rodando fonte: {src}")
            ok, output = await _run_single(src)
            if ok:
                results.append(f"[{src}] ✅ {output}")
                logger.info(f"[Scraper] ✅ {src} concluído")
            else:
                errors.append(f"[{src}] ❌ {output}")
                logger.error(f"[Scraper] ❌ {src} falhou: {output}")

        _status.last_result = "\n".join(results) or None
        _status.last_error  = "\n".join(errors)  or None

    except Exception as e:
        _status.last_error = str(e)
        logger.error(f"[Scraper] ❌ Exceção: {e}")
    finally:
        _status.running  = False
        _status.last_run = datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scraper/run", summary="Dispara o scraper em background")
async def run_scraper(
    background_tasks: BackgroundTasks,
    source: str = Form("all"),   # Form, não Query — recebe do Streamlit via api_post_form
):
    """
    Inicia o scraper em background. Retorna imediatamente.
    Use GET /scraper/status para acompanhar o progresso.
    """
    if _status.running:
        raise HTTPException(status_code=409, detail="Scraper já está em execução.")

    if source not in ("all", "gupy", "remoteok"):
        raise HTTPException(status_code=422, detail="source deve ser 'all', 'gupy' ou 'remoteok'")

    if not _SCRAPER_SCRIPT.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Script não encontrado: {_SCRAPER_SCRIPT}",
        )

    background_tasks.add_task(_run_scraper_task, source)
    logger.info(f"[Scraper] Tarefa enfileirada | source={source}")
    return {"message": f"Scraper iniciado (source={source}). Acompanhe em GET /scraper/status."}


@router.get("/scraper/status", summary="Status atual do scraper", response_model=ScraperStatus)
async def scraper_status():
    return _status