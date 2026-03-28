"""Tests for /voice toggle command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_update_context(user_id=123, text="/voice"):
    """Create mock Update and Context for command testing."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.message_id = 1

    context = MagicMock()
    context.bot_data = {}
    context.user_data = {}

    storage = MagicMock()
    storage.users = MagicMock()
    context.bot_data["storage"] = storage
    context.bot_data["features"] = MagicMock()

    settings = MagicMock()
    settings.enable_voice_responses = True
    settings.mistral_api_key = MagicMock()  # not None

    return update, context, storage, settings


async def test_voice_on_enables(monkeypatch):
    """'/voice on' enables voice responses for the user."""
    update, context, storage, settings = _make_update_context(text="/voice on")
    storage.users.set_voice_responses_enabled = AsyncMock()

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    storage.users.set_voice_responses_enabled.assert_called_once_with(123, True)
    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "on" in reply_text.lower() or "enabled" in reply_text.lower()


async def test_voice_off_disables(monkeypatch):
    """'/voice off' disables voice responses for the user."""
    update, context, storage, settings = _make_update_context(text="/voice off")
    storage.users.set_voice_responses_enabled = AsyncMock()

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    storage.users.set_voice_responses_enabled.assert_called_once_with(123, False)
    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "off" in reply_text.lower() or "disabled" in reply_text.lower()


async def test_voice_no_args_shows_status():
    """'/voice' with no args shows current status."""
    update, context, storage, settings = _make_update_context(text="/voice")
    storage.users.get_voice_responses_enabled = AsyncMock(return_value=False)

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    storage.users.get_voice_responses_enabled.assert_called_once_with(123)
    update.message.reply_text.assert_called_once()


async def test_voice_disabled_at_admin_level():
    """'/voice' when feature disabled at admin level shows unavailable message."""
    update, context, storage, settings = _make_update_context(text="/voice on")
    settings.enable_voice_responses = False

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "not enabled" in reply_text.lower()
