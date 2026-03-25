# ============================================================
# LangGraph StateGraph — orquestra todo o pipeline de análise.
#
# Fluxo:
#   START
#     → check_cache      (hit? → END direto)
#     → extract_cv
#     → extract_jd
#     → validate
#     → generate_report
#     → save_result
#   END
# ============================================================
from __future__ import annotations
import asyncio
from typing import Any
from uuid import UUID

from langgraph.graph import StateGraph, END
from loguru import logger

from models.agent_state import AgentState
from models.jd_model import JobDescription
from agents.cv_extraction_agent import CVExtractionAgent
from agents.jd_extraction_agent import JDExtractionAgent
from agents.conformity_validator import ConformityValidator
from agents.report_generator import ReportGenerator
from cache.validation_cache import ValidationCache
from cache.embedding_cache import EmbeddingCache
from database.connection import AsyncSessionLocal
from database.repositories.jd_repository import JDRepository
from database.repositories.result_repository import ResultRepository
from scraper.base_scraper import RawJob
from datetime import datetime


class CVConformityOrchestrator:
    """
    Orquestrador principal via LangGraph.
    Cada node é uma etapa do pipeline — análogo ao ADK do Feito/Conferido.
    """

    def __init__(
        self,
        validation_cache: ValidationCache,
        embedding_cache: EmbeddingCache,
    ):
        self._validation_cache = validation_cache
        self._embedding_cache  = embedding_cache
        self._validator        = ConformityValidator()
        self._graph            = self._build_graph()

    # ----------------------------------------------------------
    # NODES
    # ----------------------------------------------------------

    async def _node_check_cache(self, state: dict) -> dict:
        """Verifica cache antes de processar — evita retrabalho."""
        s = AgentState(**state)
        s.current_step = "check_cache"

        if not s.pdf_bytes or not s.jd_id:
            return s.model_dump()

        # Precisa do hash do PDF para checar cache
        import hashlib
        pdf_hash = hashlib.sha256(s.pdf_bytes).hexdigest()

        cached = await self._validation_cache.get(pdf_hash, s.jd_id)
        if cached:
            logger.info(f"[Orchestrator] Cache hit para hash={pdf_hash[:12]}...")
            s.conformity_result = cached
            s.cache_hit         = True
            s.cached_result_id  = cached.id
            s.current_step      = "done"
        return s.model_dump()

    async def _node_extract_cv(self, state: dict) -> dict:
        """Node de extração do CV."""
        s = AgentState(**state)
        if s.cache_hit:
            return s.model_dump()

        s.current_step = "extract_cv"
        try:
            async with CVExtractionAgent() as agent:
                s.cv_profile = await agent.extract_from_bytes(s.pdf_bytes)

            # Indexa no ChromaDB para buscas futuras
            await self._embedding_cache.upsert(s.cv_profile)

        except Exception as e:
            err = f"Falha na extração do CV: {e}"
            logger.error(f"[Orchestrator] {err}")
            s.errors.append(err)

        return s.model_dump()

    async def _node_extract_jd(self, state: dict) -> dict:
        """Node de obtenção da JD — do banco ou do texto."""
        s = AgentState(**state)
        if s.cache_hit or s.errors:
            return s.model_dump()

        s.current_step = "extract_jd"
        try:
            if s.jd_id:
                # Busca JD já estruturada no banco
                async with AsyncSessionLocal() as session:
                    repo = JDRepository(session)
                    orm  = await repo.get_by_id(s.jd_id)
                    if orm and orm.structured_data:
                        s.jd = JobDescription(**orm.structured_data)
                    else:
                        s.errors.append(f"JD {s.jd_id} não encontrada no banco")

            elif s.jd_input:
                # Extrai JD do texto via LLM
                raw_job = RawJob(
                    source="manual",
                    source_url="manual://input",
                    title="Vaga Manual",
                    company="",
                    raw_text=s.jd_input,
                    scraped_at=datetime.utcnow(),
                )
                async with JDExtractionAgent() as agent:
                    s.jd = await agent.extract(raw_job)
                if not s.jd:
                    s.errors.append("Falha ao extrair JD do texto")
        except Exception as e:
            err = f"Falha na obtenção da JD: {e}"
            logger.error(f"[Orchestrator] {err}")
            s.errors.append(err)

        return s.model_dump()

    async def _node_validate(self, state: dict) -> dict:
        """Node de validação — determinístico, sem LLM."""
        s = AgentState(**state)
        if s.cache_hit or s.errors:
            return s.model_dump()

        s.current_step = "validate"
        try:
            s.conformity_result = self._validator.validate(s.cv_profile, s.jd)
        except Exception as e:
            err = f"Falha na validação: {e}"
            logger.error(f"[Orchestrator] {err}")
            s.errors.append(err)

        return s.model_dump()

    async def _node_generate_report(self, state: dict) -> dict:
        """Node de geração do parecer — usa LLM."""
        s = AgentState(**state)
        if s.cache_hit or s.errors or not s.conformity_result:
            return s.model_dump()

        s.current_step = "generate_report"
        try:
            async with ReportGenerator() as reporter:
                s.conformity_result = await reporter.generate(s.conformity_result)
        except Exception as e:
            err = f"Falha na geração do parecer: {e}"
            logger.warning(f"[Orchestrator] {err} — usando fallback")
            s.warnings.append(err)

        return s.model_dump()

    async def _node_save_result(self, state: dict) -> dict:
        """Node de persistência — salva no banco e no cache."""
        s = AgentState(**state)
        if s.cache_hit or not s.conformity_result:
            return s.model_dump()

        s.current_step = "save_result"
        try:
            # Salva no banco
            async with AsyncSessionLocal() as session:
                repo = ResultRepository(session)
                await repo.save(s.conformity_result)
                await session.commit()

            # Salva no cache L1 + L2
            await self._validation_cache.set(s.conformity_result)

        except Exception as e:
            err = f"Falha ao salvar resultado: {e}"
            logger.error(f"[Orchestrator] {err}")
            s.warnings.append(err)    # não é crítico — resultado ainda é retornado

        s.current_step = "done"
        return s.model_dump()

    # ----------------------------------------------------------
    # EDGES (roteamento condicional)
    # ----------------------------------------------------------

    def _route_after_cache(self, state: dict) -> str:
        s = AgentState(**state)
        return "done" if s.cache_hit else "extract_cv"

    def _route_after_extract_cv(self, state: dict) -> str:
        s = AgentState(**state)
        return "error" if s.errors else "extract_jd"

    def _route_after_extract_jd(self, state: dict) -> str:
        s = AgentState(**state)
        return "error" if s.errors else "validate"

    def _route_after_validate(self, state: dict) -> str:
        s = AgentState(**state)
        return "error" if s.errors else "generate_report"

    # ----------------------------------------------------------
    # GRAPH BUILDER
    # ----------------------------------------------------------

    def _build_graph(self) -> Any:
        graph = StateGraph(dict)

        # Nodes
        graph.add_node("check_cache",     self._node_check_cache)
        graph.add_node("extract_cv",      self._node_extract_cv)
        graph.add_node("extract_jd",      self._node_extract_jd)
        graph.add_node("validate",        self._node_validate)
        graph.add_node("generate_report", self._node_generate_report)
        graph.add_node("save_result",     self._node_save_result)
        graph.add_node("done",            lambda s: s)
        graph.add_node("error",           lambda s: s)

        # Entry point
        graph.set_entry_point("check_cache")

        # Edges condicionais
        graph.add_conditional_edges("check_cache",   self._route_after_cache,
                                    {"done": "done", "extract_cv": "extract_cv"})
        graph.add_conditional_edges("extract_cv",    self._route_after_extract_cv,
                                    {"error": "error", "extract_jd": "extract_jd"})
        graph.add_conditional_edges("extract_jd",    self._route_after_extract_jd,
                                    {"error": "error", "validate": "validate"})
        graph.add_conditional_edges("validate",      self._route_after_validate,
                                    {"error": "error", "generate_report": "generate_report"})

        # Edges diretos
        graph.add_edge("generate_report", "save_result")
        graph.add_edge("save_result",     "done")
        graph.add_edge("done",            END)
        graph.add_edge("error",           END)

        return graph.compile()

    # ----------------------------------------------------------
    # ENTRY POINTS PÚBLICOS
    # ----------------------------------------------------------

    async def analyze(
        self,
        pdf_bytes: bytes,
        jd_id:    UUID | None = None,
        jd_input: str  | None = None,
    ) -> AgentState:
        """Análise 1 CV × 1 JD."""
        initial = AgentState(
            pdf_bytes=pdf_bytes,
            jd_id=jd_id,
            jd_input=jd_input,
        ).model_dump()

        final = await self._graph.ainvoke(initial)
        return AgentState(**final)

    async def batch_match(
        self,
        pdf_bytes:  bytes,
        top_k:      int = 10,
        domain:     str | None = None,
        seniority:  str | None = None,
    ) -> list[AgentState]:
        """
        Passa 1 CV e retorna análise contra as top_k JDs do banco.
        Esta é a funcionalidade de matching em lote que complementa o 1×1.
        """
        async with AsyncSessionLocal() as session:
            repo = JDRepository(session)
            jds  = await repo.list_active(
                domain=domain,
                seniority=seniority,
                limit=top_k,
            )

        if not jds:
            logger.warning("[Orchestrator] Nenhuma JD ativa encontrada no banco")
            return []

        logger.info(f"[Orchestrator] Batch match: 1 CV × {len(jds)} JDs")

        # Processa em paralelo com semáforo para não sobrecarregar o LLM
        sem = asyncio.Semaphore(2)

        async def _analyze_one(orm_jd) -> AgentState | None:
            async with sem:
                try:
                    return await self.analyze(
                        pdf_bytes=pdf_bytes,
                        jd_id=orm_jd.id,
                    )
                except Exception as e:
                    logger.error(f"[Orchestrator] Batch erro em {orm_jd.title}: {e}")
                    return None

        results = await asyncio.gather(*[_analyze_one(jd) for jd in jds])

        # Filtra erros e ordena por score decrescente
        valid = [
            r for r in results
            if r and r.conformity_result and not r.errors
        ]
        valid.sort(
            key=lambda r: r.conformity_result.overall_score,
            reverse=True,
        )
        logger.info(
            f"[Orchestrator] Batch concluído: "
            f"{len(valid)}/{len(jds)} análises bem-sucedidas"
        )
        return valid
