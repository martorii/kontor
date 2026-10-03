import json

import pytest
import structlog

from kontor.config import Settings
from kontor.logging import configure_logging


def test_json_mode_emits_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(log_format="json"))

    structlog.get_logger().info("import_started", import_id=42)

    record = json.loads(capsys.readouterr().out)
    assert record["event"] == "import_started"
    assert record["import_id"] == 42
    assert record["level"] == "info"


def test_console_mode_is_not_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(log_format="console"))

    structlog.get_logger().info("import_started")

    with pytest.raises(json.JSONDecodeError):
        json.loads(capsys.readouterr().out)


def test_log_format_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")

    assert Settings().log_format == "json"
