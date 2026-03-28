"""Tests for voice response flow in orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_orchestrator_with_voice():
    """Create orchestrator with voice responses enabled."""
    settings = MagicMock()
    settings.enable_voice_responses = True
    settings.mistral_api_key = MagicMock()
    settings.voice_response_max_length = 2000
    settings.agentic_mode = True

    storage = MagicMock()
    storage.users = MagicMock()

    deps = {"storage": storage}

    from src.bot.orchestrator import MessageOrchestrator

    orch = MessageOrchestrator(settings, deps)
    return orch, storage


def _make_update_context(storage):
    """Create mock Update and Context."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_voice = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.message_id = 1

    context = MagicMock()
    context.bot_data = {"storage": storage}
    return update, context


async def test_short_response_sends_voice():
    """Short response synthesizes and sends voice message."""
    orch, storage = _make_orchestrator_with_voice()
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=True)

    voice_handler = MagicMock()
    voice_handler.synthesize_speech = AsyncMock(return_value=b"audio-data")

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text="Hello, this is a short response.",
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is True
    voice_handler.synthesize_speech.assert_called_once_with(
        "Hello, this is a short response."
    )
    update.message.reply_voice.assert_called_once()
    # Should send a short label text too
    update.message.reply_text.assert_called_once()


async def test_voice_disabled_skips():
    """When user has voice off, returns False."""
    orch, storage = _make_orchestrator_with_voice()
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=False)
    voice_handler = MagicMock()

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text="Some response",
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is False
    voice_handler.synthesize_speech.assert_not_called()


async def test_tts_failure_falls_back_to_text():
    """TTS failure returns False so text path runs."""
    orch, storage = _make_orchestrator_with_voice()
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=True)

    voice_handler = MagicMock()
    voice_handler.synthesize_speech = AsyncMock(
        side_effect=RuntimeError("TTS failed")
    )

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text="Some response",
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is False
