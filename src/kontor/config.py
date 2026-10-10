from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_format: Literal["console", "json"] = "console"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "postgresql+psycopg://kontor:change-me@localhost:5432/kontor"
    rules_path: str = "config/rules.yaml"
    llm_base_url: str = "http://localhost:1234/v1"
    llm_model: str = ""
    llm_api_key: str = "lm-studio"
    llm_timeout_seconds: float = 60.0
    llm_confidence_threshold: float = 0.95
    llm_concurrency: int = Field(default=4, ge=1)
    llm_batch_size: int = Field(default=10, ge=1)
