# ============================================================
# Request/Response schemas da API
# ============================================================
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class AnalyzeRequest(BaseModel):
    jd_id:    Optional[UUID] = None
    jd_text:  Optional[str]  = None
    top_k:    int             = Field(default=10, ge=1, le=50)
    domain:   Optional[str]  = None
    seniority: Optional[str] = None


class DimensionScoreOut(BaseModel):
    score:      float
    weight:     float
    matched:    list[str] = []
    missing:    list[str] = []
    partial:    list[str] = []
    notes:      list[str] = []
    is_blocked: bool = False


class DimensionsOut(BaseModel):
    hard_skills: DimensionScoreOut
    experience:  DimensionScoreOut
    education:   DimensionScoreOut
    languages:   DimensionScoreOut
    soft_skills: DimensionScoreOut


class ConformityResultOut(BaseModel):
    id:                   UUID
    candidate_name:       str
    jd_title:             str
    verdict:              str
    overall_score:        float
    has_absolute_blocker: bool
    dimensions:           Optional[DimensionsOut]
    critical_gaps:        list[str]
    strengths:            list[str]
    partial_matches:      list[str]
    parecer_final_pt:     str
    parecer_final_en:     str
    analyzed_at:          datetime
    cache_hit:            bool = False


class BatchResultOut(BaseModel):
    candidate_name: str
    total_analyzed: int
    results:        list[ConformityResultOut]


class JobOut(BaseModel):
    id:                    UUID
    title:                 str
    company:               str
    domain:                Optional[str]
    seniority:             Optional[str]
    source:                str
    source_url:            Optional[str]
    min_experience_years:  Optional[float]
    extraction_confidence: Optional[float]
    scraped_at:            Optional[datetime]


class JobListOut(BaseModel):
    total:  int
    jobs:   list[JobOut]


class HealthOut(BaseModel):
    status:   str
    services: dict[str, str]
