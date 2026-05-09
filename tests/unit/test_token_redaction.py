"""Tests for defensive redaction of Telegram bot tokens in logs."""

import io
import logging

from src.main import TelegramTokenRedactionFilter, setup_logging


def test_redacts_telegram_bot_token_in_log_message() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: POST https://api.telegram.org/bot123456789:ABC_def-GHI/getMe "HTTP/1.1 200 OK"',
        args=(),
        exc_info=None,
    )

    assert TelegramTokenRedactionFilter().filter(record) is True

    rendered = record.getMessage()
    assert "bot123456789:ABC_def-GHI" not in rendered
    assert "bot<REDACTED>" in rendered


def test_redacts_telegram_bot_token_in_format_args() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: %s",
        args=("https://api.telegram.org/bot987654321:SECRET-token/deleteWebhook",),
        exc_info=None,
    )

    assert TelegramTokenRedactionFilter().filter(record) is True

    rendered = record.getMessage()
    assert "bot987654321:SECRET-token" not in rendered
    assert "bot<REDACTED>" in rendered


def test_setup_logging_redacts_propagated_httpx_records(monkeypatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr("sys.stdout", stream)

    setup_logging(debug=True)
    logging.getLogger("httpx").info(
        'HTTP Request: POST https://api.telegram.org/bot111222333:ABC_def-GHI/getMe "HTTP/1.1 200 OK"'
    )

    rendered = stream.getvalue()
    assert "bot111222333:ABC_def-GHI" not in rendered
    assert "bot<REDACTED>" in rendered
