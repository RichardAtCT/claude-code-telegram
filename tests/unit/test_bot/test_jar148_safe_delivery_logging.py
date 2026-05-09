from types import SimpleNamespace

import pytest

from src.bot.utils.formatting import ResponseFormatter
from src.config.settings import Settings


@pytest.fixture()
def formatter(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:TEST_TOKEN")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "test_bot")
    monkeypatch.setenv("APPROVED_DIRECTORY", str(tmp_path))
    return ResponseFormatter(Settings())


def test_empty_placeholder_log_omits_raw_text_preview(formatter, monkeypatch):
    events = []
    monkeypatch.setattr(
        "src.bot.utils.formatting.logger.warning",
        lambda event, **kwargs: events.append((event, kwargs)),
    )
    monkeypatch.setattr(formatter, "_split_message", lambda text: [])

    formatter.format_claude_response("secret payload that should not be logged")

    assert events
    assert events[0][0] == "format_claude_response_empty_placeholder"
    assert events[0][1]["original_text_len"] == len(
        "secret payload that should not be logged"
    )
    assert "original_first_chars" not in events[0][1]
    assert "original_last_chars" not in events[0][1]
