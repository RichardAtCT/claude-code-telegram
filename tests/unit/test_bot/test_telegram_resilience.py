"""Tests for resilient Telegram API helper."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from telegram.error import RetryAfter, TimedOut

from src.bot.utils.telegram_resilience import (
    is_transient_telegram_error,
    resilient_telegram_call,
)


@pytest.mark.asyncio
async def test_resilient_telegram_call_retries_retry_after(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.bot.utils.telegram_resilience.asyncio.sleep", fake_sleep)

    call = AsyncMock(side_effect=[RetryAfter(2), "ok"])

    result = await resilient_telegram_call(
        call,
        operation="test.operation",
        attempts=2,
    )

    assert result == "ok"
    assert call.await_count == 2
    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_resilient_telegram_call_suppresses_transient_when_requested() -> None:
    call = AsyncMock(side_effect=TimedOut("timed out"))

    result = await resilient_telegram_call(
        call,
        operation="test.operation",
        attempts=1,
        fail_silently=True,
    )

    assert result is None
    call.assert_awaited_once()


def test_is_transient_telegram_error_detects_gateway_text() -> None:
    assert is_transient_telegram_error(TimedOut("timed out"))
