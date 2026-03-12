from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # --- App ---
    app_env: str = Field("development", env="APP_ENV")
    log_level: str = Field("DEBUG", env="LOG_LEVEL")
    upload_dir: Path = Field(Path("./uploads"), env="UPLOAD_DIR")
    results_dir: Path = Field(Path("./results"), env="RESULTS_DIR")

    # --- PostgreSQL ---
    database_url: str = Field(
        "postgresql+asyncpg://cva_user:cva_pass@localhost:5432/cv_conformity",
        env="DATABASE_URL"
    )
    postgres_host: str = Field("localhost", env="POSTGRES_HOST")
    postgres_port: int = Field(5432, env="POSTGRES_PORT")
    postgres_user: str = Field("cva_user", env="POSTGRES_USER")
    postgres_password: str = Field("cva_pass", env="POSTGRES_PASSWORD")
    postgres_db: str = Field("cv_conformity", env="POSTGRES_DB")

    # --- Redis ---
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")

    # --- ChromaDB ---
    chroma_host: str = Field("localhost", env="CHROMA_HOST")
    chroma_port: int = Field(8001, env="CHROMA_PORT")

    # --- Ollama ---
    ollama_base_url: str = Field("http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field("llama3.1:8b", env="OLLAMA_MODEL")
    ollama_timeout: int = Field(120, env="OLLAMA_TIMEOUT")

    # --- Scraper ---
    scraper_cron_hour: int = Field(0, env="SCRAPER_CRON_HOUR")
    scraper_cron_minute: int = Field(0, env="SCRAPER_CRON_MINUTE")
    scraper_max_concurrent: int = Field(5, env="SCRAPER_MAX_CONCURRENT")
    scraper_delay_min: float = Field(1.0, env="SCRAPER_REQUEST_DELAY_MIN")
    scraper_delay_max: float = Field(3.0, env="SCRAPER_REQUEST_DELAY_MAX")

    # --- Scoring Thresholds ---
    score_threshold_approved: float = 70.0
    score_threshold_partial: float = 50.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"   # ignora variáveis do .env não declaradas (ex: pgadmin_*)

    def create_dirs(self):
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.create_dirs()