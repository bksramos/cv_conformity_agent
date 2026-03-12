from __future__ import annotations
from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from database.connection import Base


class CompanyORM(Base):
    __tablename__ = "companies"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    domain = Column(String(64))                      # tech, finance, health…
    website = Column(String(512))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job_descriptions = relationship("JobDescriptionORM", back_populates="company")


class JobDescriptionORM(Base):
    __tablename__ = "job_descriptions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)

    # Conteúdo
    title = Column(String(512), nullable=False, index=True)
    raw_text = Column(Text)
    structured_data = Column(JSON)                   # JobDescription serializado

    # Classificação
    domain = Column(String(32), index=True)          # TECH, DATA, BUSINESS…
    seniority = Column(String(32), index=True)       # JUNIOR, PLENO, SENIOR…

    # Scraping
    source = Column(String(64), nullable=False)      # gupy, remoteok, manual
    source_url = Column(String(1024), unique=True)
    is_active = Column(Boolean, default=True, index=True)
    scraped_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))

    # Qualidade da extração
    extraction_confidence = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    company = relationship("CompanyORM", back_populates="job_descriptions")
    analysis_results = relationship("AnalysisResultORM", back_populates="job_description")


class ScrapingLogORM(Base):
    __tablename__ = "scraping_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(64), nullable=False)

    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Float)

    jobs_found = Column(Integer, default=0)
    jobs_inserted = Column(Integer, default=0)
    jobs_duplicated = Column(Integer, default=0)
    jobs_failed = Column(Integer, default=0)

    errors = Column(JSON, default=list)
    status = Column(String(32))                      # SUCCESS | PARTIAL | FAILED

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AnalysisResultORM(Base):
    __tablename__ = "analysis_results"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cv_hash = Column(String(64), nullable=False, index=True)  # SHA256 do PDF
    jd_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("job_descriptions.id"),
        nullable=False
    )

    # Candidato
    candidate_name = Column(String(255))

    # Resultado
    verdict = Column(String(32), nullable=False, index=True)
    overall_score = Column(Float)
    has_absolute_blocker = Column(Boolean, default=False)

    # Dados completos serializados
    dimensions_data = Column(JSON)
    critical_gaps = Column(JSON, default=list)
    strengths = Column(JSON, default=list)
    partial_matches = Column(JSON, default=list)

    # Pareceres
    parecer_pt = Column(Text)
    parecer_en = Column(Text)

    # Metadados
    model_used = Column(String(64))
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    job_description = relationship("JobDescriptionORM", back_populates="analysis_results")