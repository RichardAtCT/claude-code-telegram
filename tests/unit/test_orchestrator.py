"""Tests for the MessageOrchestrator."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.orchestrator import MessageOrchestrator
from src.config import create_test_config


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def agentic_settings(tmp_dir):
    return create_test_config(approved_directory=str(tmp_dir), agentic_mode=True)


@pytest.fixture
def classic_settings(tmp_dir):
    return create_test_config(approved_directory=str(tmp_dir), agentic_mode=False)


@pytest.fixture
def deps():
    return {
        "claude_integration": MagicMock(),
        "storage": MagicMock(),
        "security_validator": MagicMock(),
        "rate_limiter": MagicMock(),
        "audit_logger": MagicMock(),
    }


def test_agentic_registers_3_commands(agentic_settings, deps):
    """Agentic mode registers only start, new, status commands."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)
    app = MagicMock()
    app.add_handler = MagicMock()

    orchestrator.register_handlers(app)

    # Collect all CommandHandler registrations
    from telegram.ext import CommandHandler

    cmd_handlers = [
        call
        for call in app.add_handler.call_args_list
        if isinstance(call[0][0], CommandHandler)
    ]
    commands = [h[0][0].commands for h in cmd_handlers]

    assert len(cmd_handlers) == 3
    assert frozenset({"start"}) in commands
    assert frozenset({"new"}) in commands
    assert frozenset({"status"}) in commands


def test_classic_registers_13_commands(classic_settings, deps):
    """Classic mode registers all 13 commands."""
    orchestrator = MessageOrchestrator(classic_settings, deps)
    app = MagicMock()
    app.add_handler = MagicMock()

    orchestrator.register_handlers(app)

    from telegram.ext import CommandHandler

    cmd_handlers = [
        call
        for call in app.add_handler.call_args_list
        if isinstance(call[0][0], CommandHandler)
    ]

    assert len(cmd_handlers) == 13


def test_agentic_registers_text_document_photo_handlers(agentic_settings, deps):
    """Agentic mode registers text, document, and photo message handlers."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)
    app = MagicMock()
    app.add_handler = MagicMock()

    orchestrator.register_handlers(app)

    from telegram.ext import CallbackQueryHandler, MessageHandler

    msg_handlers = [
        call
        for call in app.add_handler.call_args_list
        if isinstance(call[0][0], MessageHandler)
    ]
    cb_handlers = [
        call
        for call in app.add_handler.call_args_list
        if isinstance(call[0][0], CallbackQueryHandler)
    ]

    # 3 message handlers (text, document, photo)
    assert len(msg_handlers) == 3
    # 1 callback handler (for cd: only)
    assert len(cb_handlers) == 1


async def test_agentic_bot_commands(agentic_settings, deps):
    """Agentic mode returns 3 bot commands."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)
    commands = await orchestrator.get_bot_commands()

    assert len(commands) == 3
    cmd_names = [c.command for c in commands]
    assert cmd_names == ["start", "new", "status"]


async def test_classic_bot_commands(classic_settings, deps):
    """Classic mode returns 13 bot commands."""
    orchestrator = MessageOrchestrator(classic_settings, deps)
    commands = await orchestrator.get_bot_commands()

    assert len(commands) == 13
    cmd_names = [c.command for c in commands]
    assert "start" in cmd_names
    assert "help" in cmd_names
    assert "git" in cmd_names


async def test_agentic_start_no_keyboard(agentic_settings, deps):
    """Agentic /start sends brief message without inline keyboard."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    update = MagicMock()
    update.effective_user.first_name = "Alice"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"settings": agentic_settings}
    for k, v in deps.items():
        context.bot_data[k] = v

    await orchestrator.agentic_start(update, context)

    update.message.reply_text.assert_called_once()
    call_kwargs = update.message.reply_text.call_args
    # No reply_markup argument (no keyboard)
    assert (
        "reply_markup" not in call_kwargs.kwargs
        or call_kwargs.kwargs.get("reply_markup") is None
    )
    # Contains user name
    assert "Alice" in call_kwargs.args[0]


async def test_agentic_new_resets_session(agentic_settings, deps):
    """Agentic /new clears session and sends brief confirmation."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    update = MagicMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"claude_session_id": "old-session-123"}

    await orchestrator.agentic_new(update, context)

    assert context.user_data["claude_session_id"] is None
    update.message.reply_text.assert_called_once_with("Session reset. What's next?")


async def test_agentic_status_compact(agentic_settings, deps):
    """Agentic /status returns compact one-line status."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"rate_limiter": None}

    await orchestrator.agentic_status(update, context)

    call_args = update.message.reply_text.call_args
    text = call_args.args[0]
    assert "Session: none" in text


async def test_agentic_text_calls_claude(agentic_settings, deps):
    """Agentic text handler calls Claude and returns response without keyboard."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    # Mock Claude response
    mock_response = MagicMock()
    mock_response.session_id = "session-abc"
    mock_response.content = "Hello, I can help with that!"
    mock_response.tools_used = []

    claude_integration = AsyncMock()
    claude_integration.run_command = AsyncMock(return_value=mock_response)

    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "Help me with this code"
    update.message.message_id = 1
    update.message.chat.send_action = AsyncMock()
    update.message.reply_text = AsyncMock()

    # Progress message mock
    progress_msg = AsyncMock()
    progress_msg.delete = AsyncMock()
    update.message.reply_text.return_value = progress_msg

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {
        "settings": agentic_settings,
        "claude_integration": claude_integration,
        "storage": None,
        "rate_limiter": None,
        "audit_logger": None,
    }

    await orchestrator.agentic_text(update, context)

    # Claude was called
    claude_integration.run_command.assert_called_once()

    # Session ID updated
    assert context.user_data["claude_session_id"] == "session-abc"

    # Progress message deleted
    progress_msg.delete.assert_called_once()

    # Response sent without keyboard (reply_markup=None)
    response_calls = [
        c
        for c in update.message.reply_text.call_args_list
        if c != update.message.reply_text.call_args_list[0]
    ]
    for call in response_calls:
        assert call.kwargs.get("reply_markup") is None


async def test_agentic_callback_scoped_to_cd_pattern(agentic_settings, deps):
    """Agentic callback handler is registered with cd: pattern filter."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)
    app = MagicMock()
    app.add_handler = MagicMock()

    orchestrator.register_handlers(app)

    from telegram.ext import CallbackQueryHandler

    cb_handlers = [
        call[0][0]
        for call in app.add_handler.call_args_list
        if isinstance(call[0][0], CallbackQueryHandler)
    ]

    assert len(cb_handlers) == 1
    # The pattern attribute should match cd: prefixed data
    assert cb_handlers[0].pattern is not None
    assert cb_handlers[0].pattern.match("cd:my_project")


async def test_agentic_document_rejects_large_files(agentic_settings, deps):
    """Agentic document handler rejects files over 10MB."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    update = MagicMock()
    update.effective_user.id = 123
    update.message.document.file_name = "big.bin"
    update.message.document.file_size = 20 * 1024 * 1024  # 20MB
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"security_validator": None}

    await orchestrator.agentic_document(update, context)

    call_args = update.message.reply_text.call_args
    assert "too large" in call_args.args[0].lower()


async def test_agentic_start_escapes_html_in_name(agentic_settings, deps):
    """Names with HTML-special characters are escaped safely."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    update = MagicMock()
    update.effective_user.first_name = "A<B>&C"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    await orchestrator.agentic_start(update, context)

    call_kwargs = update.message.reply_text.call_args
    text = call_kwargs.args[0]
    # HTML-special characters should be escaped
    assert "A&lt;B&gt;&amp;C" in text
    # parse_mode is HTML
    assert call_kwargs.kwargs.get("parse_mode") == "HTML"


async def test_agentic_text_logs_failure_on_error(agentic_settings, deps):
    """Failed Claude runs are logged with success=False."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    claude_integration = AsyncMock()
    claude_integration.run_command = AsyncMock(side_effect=Exception("Claude broke"))

    audit_logger = AsyncMock()
    audit_logger.log_command = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "do something"
    update.message.message_id = 1
    update.message.chat.send_action = AsyncMock()
    update.message.reply_text = AsyncMock()

    progress_msg = AsyncMock()
    progress_msg.delete = AsyncMock()
    update.message.reply_text.return_value = progress_msg

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {
        "settings": agentic_settings,
        "claude_integration": claude_integration,
        "storage": None,
        "rate_limiter": None,
        "audit_logger": audit_logger,
    }

    await orchestrator.agentic_text(update, context)

    # Audit logged with success=False
    audit_logger.log_command.assert_called_once()
    call_kwargs = audit_logger.log_command.call_args
    assert call_kwargs.kwargs["success"] is False
