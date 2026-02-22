"""Tests for bot core rate limiter wiring."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import AIORateLimiter

import src.bot.core as core_module
from src.bot.core import ClaudeCodeBot
from src.config import create_test_config


@pytest.fixture
def bot_with_builder(monkeypatch):
    """Create a bot with mocked Application builder plumbing."""
    settings = create_test_config()
    deps = {
        "storage": MagicMock(),
        "security_validator": MagicMock(),
    }
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
    app.add_handler = MagicMock()
    app.add_error_handler = MagicMock()
    builder.build.return_value = app

    monkeypatch.setattr(
        core_module.Application,
        "builder",
        MagicMock(return_value=builder),
    )
    monkeypatch.setattr(
        core_module,
        "FeatureRegistry",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(bot, "_set_bot_commands", AsyncMock())
    monkeypatch.setattr(bot, "_register_handlers", MagicMock())
    monkeypatch.setattr(bot, "_add_middleware", MagicMock())

    return bot, builder


@pytest.mark.asyncio
async def test_initialize_sets_aioratelimiter_with_single_retry(bot_with_builder):
    """Bot initialize should configure PTB AIORateLimiter(max_retries=1)."""
    bot, builder = bot_with_builder

    await bot.initialize()

    builder.rate_limiter.assert_called_once()
    limiter = builder.rate_limiter.call_args.args[0]
    assert isinstance(limiter, AIORateLimiter)
    assert limiter._max_retries == 1


@pytest.mark.asyncio
async def test_initialize_is_idempotent_and_builds_once(bot_with_builder):
    """Repeated initialize calls should not rebuild the app."""
    bot, builder = bot_with_builder

    await bot.initialize()
    await bot.initialize()

    builder.build.assert_called_once()
    builder.rate_limiter.assert_called_once()
    bot._set_bot_commands.assert_awaited_once()
    bot._register_handlers.assert_called_once()
    bot._add_middleware.assert_called_once()
