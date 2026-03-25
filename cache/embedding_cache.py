# ============================================================
# ChromaDB — armazena embeddings de CVs já processados.
# Permite buscar CVs similares e evitar re-extração.
# ============================================================
from __future__ import annotations
import hashlib
import json
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions
from loguru import logger

from config.settings import settings
from config.feature_flags import flags
from models.cv_model import CVProfile


class EmbeddingCache:
    """
    Armazena e busca CVs por similaridade semântica via ChromaDB.
    Usa embeddings locais (sentence-transformers) — sem custo.
    """

    COLLECTION_NAME = "cv_profiles"

    def __init__(self):
        self._client: Optional[chromadb.AsyncHttpClient] = None
        self._collection = None

    async def connect(self):
        if not flags.USE_EMBEDDING_CACHE:
            return
        try:
            self._client = await chromadb.AsyncHttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
            )
            # Embedding function local — não precisa de API key
            ef = embedding_functions.DefaultEmbeddingFunction()
            self._collection = await self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            count = await self._collection.count()
            logger.info(f"[EmbeddingCache] ChromaDB conectado — {count} CVs indexados")
        except Exception as e:
            logger.warning(f"[EmbeddingCache] ChromaDB indisponível: {e}")
            self._collection = None

    async def upsert(self, profile: CVProfile):
        """Indexa ou atualiza o CV no ChromaDB."""
        if not self._collection:
            return
        try:
            text = self._profile_to_text(profile)
            await self._collection.upsert(
                ids=[profile.pdf_hash],
                documents=[text],
                metadatas=[{
                    "candidate_name":      profile.candidate_name,
                    "seniority":           profile.seniority_inferred.value,
                    "total_exp_years":     str(profile.total_experience_years),
                    "extraction_confidence": str(profile.extraction_confidence),
                }],
            )
            logger.debug(f"[EmbeddingCache] CV indexado: {profile.candidate_name}")
        except Exception as e:
            logger.warning(f"[EmbeddingCache] Erro ao indexar CV: {e}")

    async def get_by_hash(self, pdf_hash: str) -> Optional[dict]:
        """Verifica se um CV já foi indexado pelo hash do PDF."""
        if not self._collection:
            return None
        try:
            result = await self._collection.get(ids=[pdf_hash])
            if result and result["ids"]:
                return result["metadatas"][0] if result["metadatas"] else {}
            return None
        except Exception:
            return None

    async def find_similar_cvs(self, query_text: str, n_results: int = 5) -> list[dict]:
        """Busca CVs similares por texto — útil para clustering futuro."""
        if not self._collection:
            return []
        try:
            results = await self._collection.query(
                query_texts=[query_text],
                n_results=n_results,
            )
            return [
                {"hash": id_, "metadata": meta, "distance": dist}
                for id_, meta, dist in zip(
                    results["ids"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )
            ]
        except Exception as e:
            logger.warning(f"[EmbeddingCache] Erro na busca: {e}")
            return []

    def _profile_to_text(self, p: CVProfile) -> str:
        """Converte CVProfile em texto para geração de embedding."""
        skills = " ".join(s.name for s in p.hard_skills)
        roles  = " ".join(e.role for e in p.experiences)
        techs  = " ".join(
            t for e in p.experiences for t in e.technologies
        )
        return (
            f"{p.candidate_name} {p.seniority_inferred.value} "
            f"{p.total_experience_years} anos {skills} {roles} {techs} "
            f"{p.summary or ''}"
        ).strip()
