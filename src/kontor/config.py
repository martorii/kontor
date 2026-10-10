from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """A required setting is missing; the process must not start."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_format: Literal["console", "json"] = "console"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "postgresql+psycopg://kontor:change-me@localhost:5432/kontor"
    rules_path: str = "config/rules.yaml"
    # Required by the API and `make eval` (see require_categorizer_llm), but not by Alembic,
    # so they have no default and an empty value means "not set".
    categorizer_llm_base_url: str = ""
    categorizer_llm_model: str = ""
    categorizer_llm_api_key: str = "lm-studio"
    categorizer_llm_timeout_seconds: float = 60.0
    categorizer_llm_confidence_threshold: float = 0.95
    categorizer_llm_concurrency: int = Field(default=4, ge=1)
    categorizer_llm_batch_size: int = Field(default=10, ge=1)
    agent_statement_timeout_seconds: float = Field(default=10.0, gt=0)
    agent_max_rows: int = Field(default=500, ge=1)
    # The agent's own LM Studio model (CONTRACT §16.8); no fallback to the categorizer's.
    # Required once the agent is wired into the API (Step 28).
    agent_llm_base_url: str = ""
    agent_llm_model: str = ""
    agent_llm_api_key: str = "lm-studio"
    agent_llm_timeout_seconds: float = Field(default=120.0, gt=0)
    agent_max_retries: int = Field(default=2, ge=0)
    agent_summary_rows: int = Field(default=50, ge=1)
    agent_max_turns: int = Field(default=10, ge=1)
    agent_conversation_ttl_minutes: int = Field(default=60, ge=1)

    def require_categorizer_llm(self) -> None:
        """Raise ConfigurationError unless the categorizer's LM Studio URL and model are set."""
        missing = [
            name
            for name, value in (
                ("CATEGORIZER_LLM_BASE_URL", self.categorizer_llm_base_url),
                ("CATEGORIZER_LLM_MODEL", self.categorizer_llm_model),
            )
            if not value.strip()
        ]
        if missing:
            raise ConfigurationError(f"{' and '.join(missing)} must be set (see .env.example).")
