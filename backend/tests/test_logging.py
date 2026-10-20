import json
import logging

import pytest
import structlog

from lumen.logging_config import configure_logging


def _last_json_line(captured: str) -> dict[str, object]:
    lines = [line for line in captured.splitlines() if line.strip()]
    result: dict[str, object] = json.loads(lines[-1])
    return result


def test_structlog_events_are_rendered_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=True)

    structlog.get_logger("lumen.test").info("document_uploaded", document_id=42)

    entry = _last_json_line(capsys.readouterr().out)
    assert entry["event"] == "document_uploaded"
    assert entry["document_id"] == 42
    assert entry["level"] == "info"
    assert entry["logger"] == "lumen.test"
    assert "timestamp" in entry


def test_stdlib_loggers_are_rendered_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=True)

    logging.getLogger("uvicorn.error").warning("server %s", "starting")

    entry = _last_json_line(capsys.readouterr().out)
    assert entry["event"] == "server starting"
    assert entry["level"] == "warning"
