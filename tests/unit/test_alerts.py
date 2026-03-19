"""Tests for the alerts module: AlertManager."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifications.alerts import AlertManager


@pytest.fixture
def alert_manager():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    event_bus = MagicMock()
    event_bus.publish = AsyncMock()
    return AlertManager(
        bot=bot,
        event_bus=event_bus,
        admin_chat_ids=[111],
        cost_threshold_per_user=10.0,
        cost_threshold_global=100.0,
        error_rate_threshold=3,
        error_rate_window_seconds=300,
        cooldown_seconds=60,
    )


# ---------------------------------------------------------------------------
# Cost alerts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_alert_triggers_on_threshold(alert_manager):
    await alert_manager.check_cost_alert(user_id=1, current_cost=15.0)

    # Should have sent an alert (per-user threshold exceeded)
    alert_manager._bot.send_message.assert_awaited()
    call_args = alert_manager._bot.send_message.call_args
    assert "User 1" in call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_cost_alert_not_triggered_below_threshold(alert_manager):
    await alert_manager.check_cost_alert(user_id=1, current_cost=5.0)
    alert_manager._bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# Alert deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_deduplication(alert_manager):
    await alert_manager.check_cost_alert(user_id=1, current_cost=15.0)
    first_call_count = alert_manager._bot.send_message.await_count

    # Second call within cooldown should be suppressed
    await alert_manager.check_cost_alert(user_id=1, current_cost=15.0)
    assert alert_manager._bot.send_message.await_count == first_call_count


@pytest.mark.asyncio
async def test_alert_fires_again_after_cooldown(alert_manager):
    await alert_manager.check_cost_alert(user_id=1, current_cost=15.0)
    first_count = alert_manager._bot.send_message.await_count

    # Simulate cooldown elapsed by manipulating history
    for key in alert_manager._alert_history:
        alert_manager._alert_history[key] = time.time() - 120

    await alert_manager.check_cost_alert(user_id=1, current_cost=15.0)
    assert alert_manager._bot.send_message.await_count > first_count


# ---------------------------------------------------------------------------
# Error rate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_rate_triggers_on_threshold(alert_manager):
    for _ in range(3):
        await alert_manager.check_error_rate()

    # After 3 errors (threshold), an alert should be sent
    alert_manager._bot.send_message.assert_awaited()
    call_text = alert_manager._bot.send_message.call_args.kwargs["text"]
    assert "Error rate" in call_text or "error" in call_text.lower()


@pytest.mark.asyncio
async def test_error_rate_no_alert_below_threshold(alert_manager):
    await alert_manager.check_error_rate()
    await alert_manager.check_error_rate()
    # Only 2 errors, threshold is 3
    alert_manager._bot.send_message.assert_not_awaited()
