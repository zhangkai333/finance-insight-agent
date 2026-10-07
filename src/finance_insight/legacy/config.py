from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FinAgent Insight"
    app_env: str = "development"
    database_path: Path = Path("data/legacy/finagent_runtime.db")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    llm_circuit_reset_seconds: int = Field(default=60, ge=1, le=600)
    max_upload_mb: int = Field(default=20, ge=1, le=100)
    max_agent_retries: int = Field(default=1, ge=0, le=3)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()

