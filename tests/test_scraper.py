import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from scraper.base_scraper import RawJob
from scraper.normalizer import JobNormalizer
from scraper.deduplicator import JobDeduplicator


# --- Fixtures ---

def make_raw_job(
    title="Desenvolvedor Python Sênior",
    company="TechCorp",
    raw_text="Buscamos desenvolvedor com experiência em Python, FastAPI e PostgreSQL.",
    source="gupy",
    source_url="https://portal.gupy.io/job/12345",
) -> RawJob:
    return RawJob(
        source=source,
        source_url=source_url,
        title=title,
        company=company,
        raw_text=raw_text,
        scraped_at=datetime.utcnow(),
    )


# --- Normalizer ---

class TestJobNormalizer:
    def setup_method(self):
        self.normalizer = JobNormalizer()

    def test_removes_html_tags(self):
        job = make_raw_job(raw_text="<p>Experiência em <strong>Python</strong></p>")
        result = self.normalizer.normalize(job)
        assert "<p>" not in result.raw_text
        assert "<strong>" not in result.raw_text
        assert "Python" in result.raw_text

    def test_normalizes_bullets(self):
        job = make_raw_job(raw_text="• Python\n▸ FastAPI\n➤ PostgreSQL")
        result = self.normalizer.normalize(job)
        assert "•" not in result.raw_text
        assert "▸" not in result.raw_text

    def test_truncates_long_text(self):
        job = make_raw_job(raw_text="x" * 10000)
        result = self.normalizer.normalize(job)
        assert len(result.raw_text) <= 8100  # limite + "[texto truncado]"
        assert "truncado" in result.raw_text

    def test_build_llm_input_contains_all_fields(self):
        job = make_raw_job()
        llm_input = self.normalizer.build_llm_input(job)
        assert "TÍTULO DA VAGA:" in llm_input
        assert "EMPRESA:" in llm_input
        assert "FONTE:" in llm_input
        assert "DESCRIÇÃO COMPLETA:" in llm_input

    def test_clean_title_strips_whitespace(self):
        job = make_raw_job(title="  Desenvolvedor  Python  ")
        result = self.normalizer.normalize(job)
        assert result.title == "Desenvolvedor  Python"


# --- Deduplicator ---

class TestJobDeduplicator:

    @pytest.mark.asyncio
    async def test_first_occurrence_not_duplicate(self):
        session = MagicMock()
        dedup = JobDeduplicator(session)

        mock_repo = AsyncMock()
        mock_repo.exists_by_url.return_value = False
        dedup._repo = mock_repo

        job = make_raw_job()
        result = await dedup.is_duplicate(job)
        assert result is False

    @pytest.mark.asyncio
    async def test_same_url_twice_is_duplicate(self):
        session = MagicMock()
        dedup = JobDeduplicator(session)

        mock_repo = AsyncMock()
        mock_repo.exists_by_url.return_value = False
        dedup._repo = mock_repo

        job = make_raw_job()
        await dedup.is_duplicate(job)   # primeira vez
        result = await dedup.is_duplicate(job)  # segunda vez (in-memory)
        assert result is True
        # Deve ter chamado o banco só uma vez (segunda foi cache in-memory)
        mock_repo.exists_by_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_in_db_is_duplicate(self):
        session = MagicMock()
        dedup = JobDeduplicator(session)

        mock_repo = AsyncMock()
        mock_repo.exists_by_url.return_value = True  # já existe no banco
        dedup._repo = mock_repo

        job = make_raw_job()
        result = await dedup.is_duplicate(job)
        assert result is True

    @pytest.mark.asyncio
    async def test_filter_new_returns_only_new(self):
        session = MagicMock()
        dedup = JobDeduplicator(session)

        existing_url = "https://portal.gupy.io/job/OLD"
        new_url = "https://portal.gupy.io/job/NEW"

        async def mock_exists(url):
            return url == existing_url

        mock_repo = AsyncMock()
        mock_repo.exists_by_url.side_effect = mock_exists
        dedup._repo = mock_repo

        jobs = [
            make_raw_job(source_url=existing_url),
            make_raw_job(source_url=new_url),
        ]
        new_jobs, duplicates = await dedup.filter_new(jobs)
        assert len(new_jobs) == 1
        assert duplicates == 1
        assert new_jobs[0].source_url == new_url