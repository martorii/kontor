import pytest
from pydantic import ValidationError

from kontor.config import Settings


def test_llm_concurrency_defaults_to_four() -> None:
    assert Settings(_env_file=None).llm_concurrency == 4  # type: ignore[call-arg]


def test_llm_concurrency_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_CONCURRENCY", "2")
    assert Settings(_env_file=None).llm_concurrency == 2  # type: ignore[call-arg]


def test_agent_query_limits_default_to_contract_values() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.agent_statement_timeout_seconds == 10.0
    assert settings.agent_max_rows == 500


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AGENT_STATEMENT_TIMEOUT_SECONDS", "0"),
        ("AGENT_STATEMENT_TIMEOUT_SECONDS", "-1"),
        ("AGENT_MAX_ROWS", "0"),
    ],
)
def test_agent_query_limits_must_be_positive(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
