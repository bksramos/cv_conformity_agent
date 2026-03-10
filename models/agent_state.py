from __future__ import annotations
from typing import Optional, Annotated
from uuid import UUID
from pydantic import BaseModel
from langgraph.graph.message import add_messages
from models.cv_model import CVProfile
from models.jd_model import JobDescription
from models.conformity_result import ConformityResult
from models.verdict import Verdict


class AgentState(BaseModel):
    """
    Estado compartilhado que flui pelo LangGraph StateGraph.
    Cada node lê e escreve neste estado — análogo ao state do ADK
    no Agent Feito/Conferido.
    """

    # --- Inputs ---
    pdf_bytes: Optional[bytes] = None               # bytes do PDF do CV
    pdf_filename: str = ""
    jd_input: Optional[str] = None                  # texto da JD ou ID do banco
    jd_id: Optional[UUID] = None                    # se buscar do banco

    # --- Extração ---
    cv_profile: Optional[CVProfile] = None
    jd: Optional[JobDescription] = None
    extraction_errors: list[str] = []

    # --- Validação ---
    conformity_result: Optional[ConformityResult] = None

    # --- Controle de fluxo ---
    current_step: str = "START"
    errors: list[str] = []
    warnings: list[str] = []
    should_retry: bool = False
    retry_count: int = 0
    max_retries: int = 2

    # --- Cache ---
    cache_hit: bool = False
    cached_result_id: Optional[UUID] = None

    class Config:
        arbitrary_types_allowed = True