import pytest
import json
from unittest.mock import AsyncMock, patch
from pathlib import Path

from extractors.text_cleaner import CVTextCleaner
from extractors.section_detector import CVSectionDetector
from agents.cv_extraction_agent import CVExtractionAgent
from models.verdict import SeniorityLevel, SkillLevel


SAMPLE_CV_TEXT = """
João Silva
joao.silva@email.com | +55 11 99999-9999 | São Paulo, SP
linkedin.com/in/joaosilva

RESUMO
Desenvolvedor Python com 6 anos de experiência em backend e APIs REST.

EXPERIÊNCIA PROFISSIONAL

TechCorp — Desenvolvedor Backend Sênior
Jan 2021 – Atual
- Desenvolvimento de APIs REST com FastAPI e Python
- Banco de dados PostgreSQL e Redis
- Deploy em AWS com Docker e Kubernetes

StartupXYZ — Desenvolvedor Pleno
Mar 2018 – Dez 2020
- Desenvolvimento com Django e Python
- Integração com APIs externas

FORMAÇÃO
Bacharelado em Ciência da Computação — USP — 2018

HABILIDADES
Python (avançado), FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS

IDIOMAS
Inglês — Avançado
Espanhol — Básico
"""

SAMPLE_LLM_RESPONSE = json.dumps({
    "candidate_name": "João Silva",
    "email": "joao.silva@email.com",
    "phone": "+55 11 99999-9999",
    "location": "São Paulo, SP",
    "linkedin_url": "linkedin.com/in/joaosilva",
    "summary": "Desenvolvedor Python com 6 anos de experiência em backend e APIs REST.",
    "hard_skills": [
        {"name": "Python", "level": "AVANCADO", "years_of_use": 6, "mentioned_in_experience": True, "aliases": ["py"]},
        {"name": "FastAPI", "level": "NAO_INFORMADO", "years_of_use": None, "mentioned_in_experience": True, "aliases": []},
        {"name": "PostgreSQL", "level": "NAO_INFORMADO", "years_of_use": None, "mentioned_in_experience": True, "aliases": []},
        {"name": "Docker", "level": "NAO_INFORMADO", "years_of_use": None, "mentioned_in_experience": True, "aliases": []},
    ],
    "soft_skills": ["comunicação", "trabalho em equipe"],
    "experiences": [
        {
            "company": "TechCorp",
            "role": "Desenvolvedor Backend Sênior",
            "start_date": "2021-01",
            "end_date": None,
            "is_current": True,
            "duration_months": 50,
            "description": "Desenvolvimento de APIs REST com FastAPI e Python",
            "technologies": ["FastAPI", "Python", "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS"],
            "domain": "tech"
        },
        {
            "company": "StartupXYZ",
            "role": "Desenvolvedor Pleno",
            "start_date": "2018-03",
            "end_date": "2020-12",
            "is_current": False,
            "duration_months": 33,
            "description": "Desenvolvimento com Django e Python",
            "technologies": ["Django", "Python"],
            "domain": "tech"
        }
    ],
    "education": [
        {
            "degree": "Bacharelado",
            "field_of_study": "Ciência da Computação",
            "institution": "USP",
            "graduation_year": 2018,
            "is_complete": True
        }
    ],
    "certifications": [],
    "languages": [
        {"name": "Inglês", "proficiency": "AVANCADO", "certified": False},
        {"name": "Espanhol", "proficiency": "BASICO", "certified": False}
    ],
    "seniority_inferred": "SENIOR",
    "total_experience_years": 6.9,
    "extraction_confidence": 0.95
})


# --- TextCleaner ---

class TestCVTextCleaner:

    def setup_method(self):
        self.cleaner = CVTextCleaner()

    def test_removes_page_numbers(self):
        text = "Experiência\n\n2\n\nFormação"
        result = self.cleaner.clean(text)
        assert "\n2\n" not in result

    def test_normalizes_bullets(self):
        text = "• Python\n▸ FastAPI\n➤ Docker"
        result = self.cleaner.clean(text)
        assert "•" not in result
        assert "Python" in result

    def test_truncates_long_text(self):
        text = "x" * 15000
        result = self.cleaner.clean(text)
        assert len(result) <= 12100
        assert "truncado" in result

    def test_extract_contact_hints_finds_email(self):
        hints = self.cleaner.extract_contact_hints(SAMPLE_CV_TEXT)
        assert "joao.silva@email.com" in hints["emails"]

    def test_extract_contact_hints_finds_linkedin(self):
        hints = self.cleaner.extract_contact_hints(SAMPLE_CV_TEXT)
        assert any("linkedin" in url for url in hints["urls"])


# --- SectionDetector ---

class TestCVSectionDetector:

    def setup_method(self):
        self.detector = CVSectionDetector()

    def test_detects_experience_section(self):
        sections = self.detector.detect(SAMPLE_CV_TEXT)
        assert "experience" in sections
        assert "TechCorp" in sections["experience"]

    def test_detects_education_section(self):
        sections = self.detector.detect(SAMPLE_CV_TEXT)
        assert "education" in sections
        assert "USP" in sections["education"]

    def test_detects_skills_section(self):
        sections = self.detector.detect(SAMPLE_CV_TEXT)
        assert "skills" in sections
        assert "Python" in sections["skills"]

    def test_detects_languages_section(self):
        sections = self.detector.detect(SAMPLE_CV_TEXT)
        assert "languages" in sections

    def test_fallback_to_full_text_when_no_sections(self):
        sections = self.detector.detect("texto sem seções claras aqui")
        assert "full_text" in sections

    def test_build_structured_input_labels_sections(self):
        sections = self.detector.detect(SAMPLE_CV_TEXT)
        structured = self.detector.build_structured_input(sections)
        assert "EXPERIÊNCIA PROFISSIONAL" in structured
        assert "FORMAÇÃO ACADÊMICA" in structured


# --- CVExtractionAgent ---

class TestCVExtractionAgent:

    @pytest.mark.asyncio
    async def test_extract_returns_cv_profile(self):
        agent = CVExtractionAgent()
        agent._client = AsyncMock()
        agent._call_llm = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)

        # Gera PDF fake com texto suficiente
        with patch.object(agent._pdf_extractor, "extract") as mock_extract:
            from extractors.pdf_extractor import RawCVText
            mock_extract.return_value = RawCVText(
                text=SAMPLE_CV_TEXT,
                pdf_hash="abc123",
                num_pages=1,
                strategy="pymupdf",
                warnings=[],
            )
            profile = await agent.extract_from_bytes(b"fake_pdf")

        assert profile.candidate_name == "João Silva"
        assert profile.email == "joao.silva@email.com"
        assert profile.seniority_inferred == SeniorityLevel.SENIOR
        assert profile.total_experience_years > 0
        assert len(profile.hard_skills) == 4
        assert len(profile.experiences) == 2
        assert len(profile.languages) == 2

    @pytest.mark.asyncio
    async def test_extract_marks_skills_mentioned_in_experience(self):
        agent = CVExtractionAgent()
        agent._call_llm = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)

        with patch.object(agent._pdf_extractor, "extract") as mock_extract:
            from extractors.pdf_extractor import RawCVText
            mock_extract.return_value = RawCVText(
                text=SAMPLE_CV_TEXT,
                pdf_hash="abc123",
                num_pages=1,
                strategy="pymupdf",
                warnings=[],
            )
            profile = await agent.extract_from_bytes(b"fake_pdf")

        python_skill = next((s for s in profile.hard_skills if s.name == "Python"), None)
        assert python_skill is not None
        assert python_skill.mentioned_in_experience is True

    @pytest.mark.asyncio
    async def test_extract_handles_llm_failure(self):
        agent = CVExtractionAgent()
        agent._call_llm = AsyncMock(return_value=None)

        with patch.object(agent._pdf_extractor, "extract") as mock_extract:
            from extractors.pdf_extractor import RawCVText
            mock_extract.return_value = RawCVText(
                text=SAMPLE_CV_TEXT,
                pdf_hash="abc123",
                num_pages=1,
                strategy="pymupdf",
                warnings=[],
            )
            profile = await agent.extract_from_bytes(b"fake_pdf")

        assert profile.candidate_name == "Desconhecido"
        assert profile.extraction_confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_injects_email_from_hints(self):
        """Se LLM não encontrar email, deve ser injetado pelos hints do PDF."""
        agent = CVExtractionAgent()
        response_without_email = json.loads(SAMPLE_LLM_RESPONSE)
        response_without_email["email"] = None
        agent._call_llm = AsyncMock(return_value=json.dumps(response_without_email))

        with patch.object(agent._pdf_extractor, "extract") as mock_extract:
            from extractors.pdf_extractor import RawCVText
            mock_extract.return_value = RawCVText(
                text=SAMPLE_CV_TEXT,
                pdf_hash="abc123",
                num_pages=1,
                strategy="pymupdf",
                warnings=[],
            )
            profile = await agent.extract_from_bytes(b"fake_pdf")

        assert profile.email == "joao.silva@email.com"
