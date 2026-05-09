"""Regression tests for JAR-149 media-derived prompts preserving thread context."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.orchestrator import MessageOrchestrator
from src.claude.sdk_integration import ClaudeResponse
from src.config import create_test_config


@pytest.fixture
def settings(tmp_path: Path):
    return create_test_config(
        approved_directory=str(tmp_path),
        agentic_mode=True,
        enable_project_threads=False,
    )


def _context(initial_user_data=None):
    context = MagicMock()
    context.bot_data = {}
    context.user_data = initial_user_data or {}
    context.bot = MagicMock()
    return context


def _voice_update(thread_id: int, reply_text: str | None = None):
    message = MagicMock()
    message.message_thread_id = thread_id
    message.direct_messages_topic = None
    message.message_id = 777
    message.caption = None
    message.voice = MagicMock()
    message.reply_text = AsyncMock()
    if reply_text is not None:
        reply = MagicMock()
        reply.text = reply_text
        reply.caption = None
        reply.voice = None
        reply.photo = None
        reply.document = None
        reply.video = None
        reply.audio = None
        reply.animation = None
        reply.message_id = 123
        reply.from_user.full_name = "Fernando T"
        message.reply_to_message = reply
    else:
        message.reply_to_message = None

    chat = MagicMock()
    chat.id = -1001234567890
    chat.type = "supergroup"
    chat.is_forum = True
    chat.send_action = AsyncMock()
    message.chat = chat

    update = MagicMock()
    update.effective_chat = chat
    update.effective_user.id = 42
    update.effective_message = message
    update.message = message
    update.callback_query = None
    return update


@pytest.mark.asyncio
async def test_agentic_voice_reuses_existing_thread_session(settings):
    """Voice prompts must run in the topic-local Claude session when one exists."""
    claude = MagicMock()
    claude.run_command = AsyncMock(
        return_value=ClaudeResponse(
            content="ok", session_id="topic-101-session", cost=0.0, duration_ms=1, num_turns=1
        )
    )
    features = MagicMock()
    voice_handler = MagicMock()
    voice_handler.process_voice_message = AsyncMock(
        return_value=SimpleNamespace(prompt="transcribed voice prompt")
    )
    features.get_voice_handler.return_value = voice_handler

    deps = {"claude_integration": claude, "features": features}
    orchestrator = MessageOrchestrator(settings, deps)
    orchestrator._send_images = AsyncMock(return_value=False)
    context = _context(
        {
            "thread_state": {
                "-1001234567890:101": {
                    "current_directory": str(settings.approved_directory),
                    "claude_session_id": "topic-101-session",
                }
            }
        }
    )

    await orchestrator._inject_deps(orchestrator.agentic_voice)(
        _voice_update(101),
        context,
    )

    kwargs = claude.run_command.await_args.kwargs
    assert kwargs["prompt"] == "transcribed voice prompt"
    assert kwargs["session_id"] == "topic-101-session"
    assert kwargs["force_new"] is False
    assert context.user_data["thread_state"]["-1001234567890:101"][
        "claude_session_id"
    ] == "topic-101-session"


@pytest.mark.asyncio
async def test_agentic_voice_forces_new_session_for_new_thread(settings):
    """A new voice-only topic must not auto-resume another topic's session."""
    claude = MagicMock()
    claude.run_command = AsyncMock(
        return_value=ClaudeResponse(
            content="ok", session_id="new-topic-session", cost=0.0, duration_ms=1, num_turns=1
        )
    )
    features = MagicMock()
    voice_handler = MagicMock()
    voice_handler.process_voice_message = AsyncMock(
        return_value=SimpleNamespace(prompt="first voice prompt")
    )
    features.get_voice_handler.return_value = voice_handler

    deps = {"claude_integration": claude, "features": features}
    orchestrator = MessageOrchestrator(settings, deps)
    orchestrator._send_images = AsyncMock(return_value=False)
    context = _context()

    await orchestrator._inject_deps(orchestrator.agentic_voice)(
        _voice_update(202),
        context,
    )

    kwargs = claude.run_command.await_args.kwargs
    assert kwargs["prompt"] == "first voice prompt"
    assert kwargs["session_id"] is None
    assert kwargs["force_new"] is True
    assert context.user_data["thread_state"]["-1001234567890:202"][
        "claude_session_id"
    ] == "new-topic-session"


@pytest.mark.asyncio
async def test_agentic_voice_passes_reply_context_to_voice_handler(settings):
    """Voice replies pass replied-message text into the transcribed prompt."""
    claude = MagicMock()
    claude.run_command = AsyncMock(
        return_value=ClaudeResponse(
            content="ok", session_id="new-topic-session", cost=0.0, duration_ms=1, num_turns=1
        )
    )
    features = MagicMock()
    voice_handler = MagicMock()
    voice_handler.process_voice_message = AsyncMock(
        return_value=SimpleNamespace(prompt="reply enriched voice prompt")
    )
    features.get_voice_handler.return_value = voice_handler

    deps = {"claude_integration": claude, "features": features}
    orchestrator = MessageOrchestrator(settings, deps)
    orchestrator._send_images = AsyncMock(return_value=False)
    context = _context()

    await orchestrator._inject_deps(orchestrator.agentic_voice)(
        _voice_update(303, reply_text="Próximo passo é tua decisão — qual caminho seguir?"),
        context,
    )

    voice_handler.process_voice_message.assert_awaited_once()
    kwargs = voice_handler.process_voice_message.await_args.kwargs
    assert kwargs["reply_context"] == "Próximo passo é tua decisão — qual caminho seguir?"
    assert claude.run_command.await_args.kwargs["prompt"] == "reply enriched voice prompt"
