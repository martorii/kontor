import pytest

from kontor.config import Settings


def test_llm_concurrency_defaults_to_four() -> None:
    assert Settings(_env_file=None).llm_concurrency == 4  # type: ignore[call-arg]


def test_llm_concurrency_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_CONCURRENCY", "2")
    assert Settings(_env_file=None).llm_concurrency == 2  # type: ignore[call-arg]
