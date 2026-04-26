"""Tests for webhook startup mode — verifies start_webhook is used instead of run_webhook."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.bot.core as core_module
from src.bot.core import ClaudeCodeBot
from src.config import create_test_config


@pytest.fixture
def bot_ready(monkeypatch):
    """Create a bot with mocked Application, already initialized."""
    settings = create_test_config()
    deps = {"storage": MagicMock(), "security": MagicMock()}
    bot = ClaudeCodeBot(settings, deps)

    builder = MagicMock()
    builder.token.return_value = builder
    builder.rate_limiter.return_value = builder
    builder.connect_timeout.return_value = builder
    builder.read_timeout.return_value = builder
    builder.write_timeout.return_value = builder
    builder.pool_timeout.return_value = builder

    app = MagicMock()
    app.bot = MagicMock()
    app.bot.set_my_commands = AsyncMock()
    app.initialize = AsyncMock()
    app.start = AsyncMock()
    app.add_handler = MagicMock()
    app.add_error_handler = MagicMock()
    builder.build.return_value = app

    monkeypatch.setattr(
        core_module.Application, "builder", MagicMock(return_value=builder)
    )
    monkeypatch.setattr(
        core_module, "FeatureRegistry", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(bot, "_set_bot_commands", AsyncMock())
    monkeypatch.setattr(bot, "_register_handlers", MagicMock())
    monkeypatch.setattr(bot, "_add_middleware", MagicMock())

    return bot, app


@pytest.mark.asyncio
async def test_webhook_mode_uses_start_webhook_not_run_webhook(bot_ready):
    """In webhook mode, start_webhook must be called instead of run_webhook.

    run_webhook manages its own event loop and raises
    'Cannot close a running event loop' when called inside asyncio.run().
    """
    bot, app = bot_ready
    bot.settings.webhook_url = "https://example.com:8443/webhook"

    # Make run_webhook raise if it's ever called (regression guard)
    app.run_webhook = AsyncMock(
        side_effect=RuntimeError("Cannot close a running event loop")
    )
    app.updater.start_webhook = AsyncMock()

    # Stop the while loop after one tick
    async def wake_after_start():
        await asyncio.sleep(0.05)
        bot.is_running = False

    asyncio.create_task(wake_after_start())

    await bot.start()

    app.run_webhook.assert_not_called()
    app.updater.start_webhook.assert_awaited_once()
    call_kwargs = app.updater.start_webhook.call_args.kwargs
    assert call_kwargs["listen"] == "0.0.0.0"
    assert call_kwargs["port"] == 8443
    assert call_kwargs["url_path"] == "/webhook"
    assert call_kwargs["webhook_url"] == "https://example.com:8443/webhook"


@pytest.mark.asyncio
async def test_polling_mode_uses_start_polling(bot_ready):
    """Polling mode should use start_polling, unchanged by the webhook fix."""
    bot, app = bot_ready
    app.updater.start_polling = AsyncMock()

    async def wake_after_start():
        await asyncio.sleep(0.05)
        bot.is_running = False

    asyncio.create_task(wake_after_start())

    await bot.start()

    app.updater.start_polling.assert_awaited_once()
    app.updater.start_webhook.assert_not_called()
    app.run_webhook.assert_not_called()
