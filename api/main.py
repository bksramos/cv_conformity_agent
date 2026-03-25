from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.dependencies import shutdown_orchestrator
from api.routes import analyze, jobs, results, health
from api.routes.cv import router as cv_router
from api.routes.cv_improvement import router as cv_improvement_router
from config.settings import settings
from api.routes.scraper import router as scraper_router
from api.routes.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 CV Conformity Agent API iniciando...")
    yield
    logger.info("🛑 CV Conformity Agent API encerrando...")
    await shutdown_orchestrator()


app = FastAPI(
    title="CV Conformity Agent API",
    description="Multi-agent system for CV × Job Description conformity analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router,  prefix="/api/v1")
app.include_router(analyze.router, prefix="/api/v1")
# app.include_router(jobs.router,    prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")
app.include_router(cv_router, prefix="/api/v1")
app.include_router(cv_improvement_router, prefix="/api/v1")
app.include_router(scraper_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
