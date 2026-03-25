# ============================================================
# Dependências compartilhadas via FastAPI DI
# ============================================================
from __future__ import annotations
from functools import lru_cache
from cache.validation_cache import ValidationCache
from cache.embedding_cache import EmbeddingCache
from agents.orchestrator import CVConformityOrchestrator

_validation_cache: ValidationCache | None = None
_embedding_cache:  EmbeddingCache  | None = None
_orchestrator:     CVConformityOrchestrator | None = None


async def get_orchestrator() -> CVConformityOrchestrator:
    global _orchestrator, _validation_cache, _embedding_cache
    if _orchestrator is None:
        _validation_cache = ValidationCache()
        _embedding_cache  = EmbeddingCache()
        await _validation_cache.connect()
        await _embedding_cache.connect()
        _orchestrator = CVConformityOrchestrator(_validation_cache, _embedding_cache)
    return _orchestrator


async def shutdown_orchestrator():
    global _validation_cache
    if _validation_cache:
        await _validation_cache.disconnect()
