import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from scraper.base_scraper import RawJob
from agents.jd_extraction_agent import JDExtractionAgent
from models.verdict import JobDomain, SeniorityLevel


SAMPLE_LLM_RESPONSE = json.dumps({
    "title": "Desenvolvedor Python Sênior",
    "company": "TechCorp",
    "domain": "TECH",
    "seniority": "SENIOR",
    "min_experience_years": 5,
    "max_experience_years": None,
    "required_skills": [
        {"name": "Python", "level": "AVANCADO", "is_required": True, "aliases": ["py"]},
        {"name": "FastAPI", "level": "INTERMEDIARIO", "is_required": True, "aliases": []},
        {"name": "Docker", "level": "NAO_INFORMADO", "is_required": False, "aliases": []},
    ],
    "education_requirements": ["Graduação em Ciência da Computação ou área correlata"],
    "certifications_required": [],
    "languages_required": [
        {"name": "Inglês", "proficiency": "INTERMEDIARIO"}
    ],
    "soft_skills_mentioned": ["comunicação", "trabalho em equipe"],
    "responsibilities": ["Desenvolver APIs REST", "Code review"],
    "extraction_confidence": 0.92
})


def make_raw_job() -> RawJob:
    return RawJob(
        source="gupy",
        source_url="https://portal.gupy.io/job/99999",
        title="Desenvolvedor Python Sênior",
        company="TechCorp",
        raw_text="Buscamos desenvolvedor Python Sênior com 5+ anos de experiência...",
        scraped_at=datetime.utcnow(),
    )


class TestJDExtractionAgent:

    @pytest.mark.asyncio
    async def test_extract_returns_job_description(self):
        agent = JDExtractionAgent()
        agent._client = AsyncMock()
        agent._call_llm = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)

        raw_job = make_raw_job()
        jd = await agent.extract(raw_job)

        assert jd is not None
        assert jd.title == "Desenvolvedor Python Sênior"
        assert jd.domain == JobDomain.TECH
        assert jd.seniority == SeniorityLevel.SENIOR
        assert jd.min_experience_years == 5.0
        assert len(jd.required_skills) == 3
        assert jd.extraction_confidence == 0.92

    @pytest.mark.asyncio
    async def test_extract_separates_required_from_desired(self):
        agent = JDExtractionAgent()
        agent._call_llm = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)

        raw_job = make_raw_job()
        jd = await agent.extract(raw_job)

        required = [s for s in jd.required_skills if s.is_required]
        desired = [s for s in jd.required_skills if not s.is_required]

        assert len(required) == 2   # Python, FastAPI
        assert len(desired) == 1    # Docker

    @pytest.mark.asyncio
    async def test_extract_handles_llm_failure(self):
        agent = JDExtractionAgent()
        agent._call_llm = AsyncMock(return_value=None)

        raw_job = make_raw_job()
        jd = await agent.extract(raw_job)

        assert jd is None

    @pytest.mark.asyncio
    async def test_extract_handles_invalid_json(self):
        agent = JDExtractionAgent()
        agent._call_llm = AsyncMock(return_value="isso não é JSON")

        raw_job = make_raw_job()
        jd = await agent.extract(raw_job)

        assert jd is None

    @pytest.mark.asyncio
    async def test_extract_handles_markdown_wrapped_json(self):
        """LLM às vezes retorna ```json ... ``` mesmo pedindo para não retornar."""
        wrapped = f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        agent = JDExtractionAgent()
        agent._call_llm = AsyncMock(return_value=wrapped)

        raw_job = make_raw_job()
        jd = await agent.extract(raw_job)

        assert jd is not None
        assert jd.title == "Desenvolvedor Python Sênior"

    def test_parse_unknown_domain_falls_back_to_other(self):
        agent = JDExtractionAgent()
        data = json.loads(SAMPLE_LLM_RESPONSE)
        data["domain"] = "DOMINIO_INEXISTENTE"
        raw_job = make_raw_job()
        jd = agent._build_jd(data, raw_job)
        assert jd.domain == JobDomain.OTHER

    def test_parse_unknown_seniority_falls_back(self):
        agent = JDExtractionAgent()
        data = json.loads(SAMPLE_LLM_RESPONSE)
        data["seniority"] = "SUPER_SENIOR"
        raw_job = make_raw_job()
        jd = agent._build_jd(data, raw_job)
        assert jd.seniority == SeniorityLevel.NAO_INFORMADO