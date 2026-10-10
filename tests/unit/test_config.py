import pytest
from pydantic import ValidationError

from kontor.api.app import create_app
from kontor.config import ConfigurationError, Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


def test_categorizer_concurrency_defaults_to_four() -> None:
    assert _settings().categorizer_llm_concurrency == 4


def test_categorizer_settings_are_read_from_their_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATEGORIZER_LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("CATEGORIZER_LLM_MODEL", "test-model")
    monkeypatch.setenv("CATEGORIZER_LLM_CONCURRENCY", "2")

    settings = _settings()

    assert settings.categorizer_llm_base_url == "http://llm.test/v1"
    assert settings.categorizer_llm_model == "test-model"
    assert settings.categorizer_llm_concurrency == 2


def test_old_llm_names_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    settings = _settings()

    assert settings.categorizer_llm_base_url == ""
    assert settings.categorizer_llm_model == ""


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        ({}, "CATEGORIZER_LLM_BASE_URL and CATEGORIZER_LLM_MODEL"),
        ({"categorizer_llm_model": "test-model"}, "CATEGORIZER_LLM_BASE_URL must"),
        ({"categorizer_llm_base_url": "http://llm.test/v1"}, "CATEGORIZER_LLM_MODEL must"),
        ({"categorizer_llm_base_url": "  ", "categorizer_llm_model": "m"}, "BASE_URL must"),
    ],
)
def test_api_refuses_to_start_without_categorizer_llm(
    overrides: dict[str, str], missing: str
) -> None:
    with pytest.raises(ConfigurationError, match=missing):
        create_app(_settings(**overrides))


def test_api_starts_with_categorizer_llm_set() -> None:
    create_app(_settings(categorizer_llm_base_url="http://llm.test/v1", categorizer_llm_model="m"))


def test_agent_query_limits_default_to_contract_values() -> None:
    settings = _settings()
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
        _settings()
