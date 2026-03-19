"""Tests for the resilience module: CircuitBreaker, RetryHandler."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.claude.resilience import (
    CircuitBreaker,
    CircuitState,
    RetryHandler,
    is_transient_error,
)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


@pytest.fixture
def breaker():
    return CircuitBreaker(threshold=3, cooldown_seconds=10)


def test_starts_closed(breaker):
    assert breaker.get_state() == CircuitState.CLOSED
    assert breaker.can_execute() is True


def test_opens_after_n_failures(breaker):
    for _ in range(3):
        breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN
    assert breaker.can_execute() is False


def test_transitions_to_half_open_after_cooldown(breaker):
    for _ in range(3):
        breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN

    # Simulate cooldown elapsed
    with patch("src.claude.resilience.time.monotonic", return_value=breaker._last_failure_time + 11):
        assert breaker.can_execute() is True
        assert breaker.get_state() == CircuitState.HALF_OPEN


def test_half_open_closes_on_success(breaker):
    for _ in range(3):
        breaker.record_failure()

    with patch("src.claude.resilience.time.monotonic", return_value=breaker._last_failure_time + 11):
        breaker.can_execute()  # transitions to HALF_OPEN

    breaker.record_success()
    assert breaker.get_state() == CircuitState.CLOSED


def test_half_open_opens_on_failure(breaker):
    for _ in range(3):
        breaker.record_failure()

    with patch("src.claude.resilience.time.monotonic", return_value=breaker._last_failure_time + 11):
        breaker.can_execute()

    breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN


def test_state_change_callback(breaker):
    states = []
    breaker.set_on_state_change(lambda s: states.append(s))

    for _ in range(3):
        breaker.record_failure()

    assert CircuitState.OPEN in states


# ---------------------------------------------------------------------------
# RetryHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_transient_error():
    handler = RetryHandler(max_retries=2, base_delay=0.01, max_delay=0.05)

    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("connection timeout")
        return "ok"

    result = await handler.execute(flaky)
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_gives_up_after_max_retries():
    handler = RetryHandler(max_retries=1, base_delay=0.01, max_delay=0.05)

    async def always_fail():
        raise ConnectionError("connection timeout")

    with pytest.raises(ConnectionError):
        await handler.execute(always_fail)


@pytest.mark.asyncio
async def test_non_transient_error_not_retried():
    handler = RetryHandler(max_retries=3, base_delay=0.01)

    call_count = 0

    async def bad():
        nonlocal call_count
        call_count += 1
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        await handler.execute(bad)

    assert call_count == 1


# ---------------------------------------------------------------------------
# is_transient_error
# ---------------------------------------------------------------------------


def test_transient_error_detection():
    assert is_transient_error(Exception("429 Too Many Requests")) is True
    assert is_transient_error(Exception("503 Service Unavailable")) is True
    assert is_transient_error(ConnectionError("connection reset")) is True
    assert is_transient_error(Exception("timeout")) is True


def test_non_transient_error():
    assert is_transient_error(ValueError("bad input")) is False
    assert is_transient_error(KeyError("missing key")) is False
