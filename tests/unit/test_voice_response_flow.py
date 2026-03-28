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
    # Short responses: audio only, no text label
    update.message.reply_text.assert_not_called()


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


async def test_long_response_summarizes_then_speaks():
    """Long response triggers summarization, sends audio of summary + full text."""
    orch, storage = _make_orchestrator_with_voice()
    orch.settings.voice_response_max_length = 50  # Low threshold for testing
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=True)

    voice_handler = MagicMock()
    voice_handler.synthesize_speech = AsyncMock(return_value=b"audio-data")

    # Mock Claude integration for summarization
    mock_claude = MagicMock()
    mock_summary_response = MagicMock()
    mock_summary_response.content = "This is a brief summary."
    mock_claude.run_command = AsyncMock(return_value=mock_summary_response)
    context.bot_data["claude_integration"] = mock_claude

    long_text = "A" * 100  # Exceeds threshold of 50

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text=long_text,
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is True
    # Should synthesize the SUMMARY, not the full text
    voice_handler.synthesize_speech.assert_called_once_with("This is a brief summary.")
    # Should send voice + text messages (full text)
    update.message.reply_voice.assert_called_once()
    assert update.message.reply_text.call_count >= 1  # Full text sent


async def test_tts_failure_falls_back_to_text():
    """TTS failure returns False and sends fallback note."""
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
    # Should have sent a fallback note
    update.message.reply_text.assert_called_once()
    note = update.message.reply_text.call_args[0][0]
    assert "audio unavailable" in note.lower()
