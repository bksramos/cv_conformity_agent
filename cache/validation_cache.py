# ============================================================
# Cache L1 (memória) + L2 (Redis) para resultados de análise.
# Chave: sha256(cv_hash + jd_id) → evita reprocessar o mesmo par
# ============================================================
from __future__ import annotations
import json
import hashlib
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from loguru import logger

from config.settings import settings
from config.feature_flags import flags
from models.conformity_result import ConformityResult


class ValidationCache:
    """
    Cache em duas camadas análogo ao do Feito/Conferido.
    L1 — dict em memória   : hit instantâneo, escopo da sessão
    L2 — Redis             : persiste entre execuções, TTL configurável
    """

    def __init__(self):
        self._l1: dict[str, ConformityResult] = {}
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        if not flags.USE_VALIDATION_CACHE:
            return
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("[ValidationCache] Redis conectado")
        except Exception as e:
            logger.warning(f"[ValidationCache] Redis indisponível — usando só L1: {e}")
            self._redis = None

    async def disconnect(self):
        if self._redis:
            await self._redis.aclose()

    def _make_key(self, cv_hash: str, jd_id: UUID) -> str:
        raw = f"{cv_hash}:{str(jd_id)}"
        return "cva:result:" + hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, cv_hash: str, jd_id: UUID) -> Optional[ConformityResult]:
        if not flags.USE_VALIDATION_CACHE:
            return None

        key = self._make_key(cv_hash, jd_id)

        # L1
        if key in self._l1:
            logger.debug(f"[ValidationCache] L1 hit: {key[:20]}...")
            return self._l1[key]

        # L2
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    result = ConformityResult(**json.loads(raw))
                    self._l1[key] = result   # promove para L1
                    logger.debug(f"[ValidationCache] L2 hit: {key[:20]}...")
                    return result
            except Exception as e:
                logger.warning(f"[ValidationCache] Erro ao ler Redis: {e}")

        return None

    async def set(self, result: ConformityResult):
        if not flags.USE_VALIDATION_CACHE:
            return

        key = self._make_key(result.cv_hash, result.jd_id)

        # L1
        self._l1[key] = result

        # L2
        if self._redis:
            try:
                await self._redis.setex(
                    key,
                    flags.CACHE_TTL_SECONDS,
                    result.model_dump_json(),
                )
                logger.debug(f"[ValidationCache] Salvo no Redis: {key[:20]}...")
            except Exception as e:
                logger.warning(f"[ValidationCache] Erro ao salvar Redis: {e}")

    async def invalidate(self, cv_hash: str, jd_id: UUID):
        key = self._make_key(cv_hash, jd_id)
        self._l1.pop(key, None)
        if self._redis:
            await self._redis.delete(key)
        logger.info(f"[ValidationCache] Cache invalidado: {key[:20]}...")

    def clear_l1(self):
        self._l1.clear()
        logger.info("[ValidationCache] L1 limpo")

