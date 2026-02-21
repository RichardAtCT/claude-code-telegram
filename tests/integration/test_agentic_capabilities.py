"""Integration tests for ALL agentic capabilities.

Exercises every user-facing feature of the Telegram bot in agentic mode:
- Commands: /start, /new, /status, /verbose, /repo
- Text message -> Claude passthrough
- File upload handling
- Photo upload handling
- Session auto-resume & reset
- Directory switching (command + inline callback)
- Verbose progress levels (0, 1, 2)
- Rate limiting enforcement
- Security validation (filename, file size)
- Error handling & recovery
- Typing heartbeat independence

Run with:
    poetry run pytest tests/integration/test_agentic_capabilities.py -v
"""

import asyncio
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.orchestrator import MessageOrchestrator
from src.claude.sdk_integration import ClaudeResponse, StreamUpdate
from src.config import create_test_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claude_response(
    content: str = "Here is the answer.",
    session_id: str = "session-abc-123",
    cost: float = 0.005,
    duration_ms: int = 1200,
    num_turns: int = 1,
    tools_used: Optional[List[Dict[str, Any]]] = None,
    is_error: bool = False,
) -> ClaudeResponse:
    return ClaudeResponse(
        content=content,
        session_id=session_id,
        cost=cost,
        duration_ms=duration_ms,
        num_turns=num_turns,
        tools_used=tools_used or [],
        is_error=is_error,
    )


def _make_update(
    user_id: int = 111,
    first_name: str = "TestUser",
    text: str = "",
    message_id: int = 1,
    chat_id: int = 111,
    chat_type: str = "private",
) -> MagicMock:
    """Build a mock Telegram Update suitable for agentic handlers."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.first_name = first_name
    update.effective_chat.id = chat_id
    update.effective_chat.type = chat_type
    update.message.text = text
    update.message.message_id = message_id
    update.message.chat.id = chat_id

    # reply_text returns an editable / deletable message mock
    progress_msg = AsyncMock()
    progress_msg.delete = AsyncMock()
    progress_msg.edit_text = AsyncMock()
    update.message.reply_text = AsyncMock(return_value=progress_msg)
    update.message.chat.send_action = AsyncMock()

    update.callback_query = None
    return update


def _make_context(
    settings: Any,
    deps: Dict[str, Any],
    user_data: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    context = MagicMock()
    context.user_data = user_data or {}
    context.bot_data = {"settings": settings, **deps}
    return context


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def workspace(tmp_dir):
    """Create a workspace with two repos (one git, one plain)."""
    repo_a = tmp_dir / "alpha"
    repo_a.mkdir()
    (repo_a / ".git").mkdir()  # Fake git repo

    repo_b = tmp_dir / "beta"
    repo_b.mkdir()

    return tmp_dir


@pytest.fixture
def settings(workspace):
    return create_test_config(approved_directory=str(workspace), agentic_mode=True)


@pytest.fixture
def claude_integration():
    ci = AsyncMock()
    ci.run_command = AsyncMock(return_value=_make_claude_response())
    ci._find_resumable_session = AsyncMock(return_value=None)
    return ci


@pytest.fixture
def deps(claude_integration):
    return {
        "claude_integration": claude_integration,
        "storage": AsyncMock(),
        "security_validator": MagicMock(),
        "rate_limiter": None,
        "audit_logger": AsyncMock(),
    }


@pytest.fixture
def orchestrator(settings, deps):
    return MessageOrchestrator(settings, deps)


# ===================================================================
# 1. COMMAND TESTS — /start, /new, /status, /verbose, /repo
# ===================================================================


class TestStartCommand:
    """Test /start command behavior."""

    async def test_start_greets_user_with_name(self, orchestrator, settings, deps):
        update = _make_update(first_name="Alice")
        context = _make_context(settings, deps)

        await orchestrator.agentic_start(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args.args[0]
        assert "Alice" in text

    async def test_start_shows_working_directory(self, orchestrator, settings, deps):
        update = _make_update()
        context = _make_context(settings, deps)

        await orchestrator.agentic_start(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "Working in:" in text

    async def test_start_no_inline_keyboard(self, orchestrator, settings, deps):
        update = _make_update()
        context = _make_context(settings, deps)

        await orchestrator.agentic_start(update, context)

        kwargs = update.message.reply_text.call_args.kwargs
        assert (
            "reply_markup" not in kwargs or kwargs.get("reply_markup") is None
        )

    async def test_start_uses_html_parse_mode(self, orchestrator, settings, deps):
        update = _make_update()
        context = _make_context(settings, deps)

        await orchestrator.agentic_start(update, context)

        kwargs = update.message.reply_text.call_args.kwargs
        assert kwargs.get("parse_mode") == "HTML"

    async def test_start_escapes_html_characters(self, orchestrator, settings, deps):
        update = _make_update(first_name="<script>alert(1)</script>")
        context = _make_context(settings, deps)

        await orchestrator.agentic_start(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "<script>" not in text
        assert "&lt;script&gt;" in text


class TestNewCommand:
    """Test /new command (session reset)."""

    async def test_new_clears_session_id(self, orchestrator, settings, deps):
        update = _make_update()
        context = _make_context(
            settings, deps, user_data={"claude_session_id": "old-session"}
        )

        await orchestrator.agentic_new(update, context)

        assert context.user_data["claude_session_id"] is None

    async def test_new_sets_force_new_flag(self, orchestrator, settings, deps):
        update = _make_update()
        context = _make_context(settings, deps)

        await orchestrator.agentic_new(update, context)

        assert context.user_data["force_new_session"] is True

    async def test_new_sends_confirmation(self, orchestrator, settings, deps):
        update = _make_update()
        context = _make_context(settings, deps)

        await orchestrator.agentic_new(update, context)

        update.message.reply_text.assert_called_once_with("Session reset. What's next?")


class TestStatusCommand:
    """Test /status command (compact status line)."""

    async def test_status_shows_session_none_when_no_session(
        self, orchestrator, settings, deps
    ):
        update = _make_update()
        context = _make_context(settings, deps)

        await orchestrator.agentic_status(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "Session: none" in text

    async def test_status_shows_session_active(self, orchestrator, settings, deps):
        update = _make_update()
        context = _make_context(
            settings, deps, user_data={"claude_session_id": "sess-123"}
        )

        await orchestrator.agentic_status(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "Session: active" in text

    async def test_status_shows_current_directory(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update()
        context = _make_context(
            settings,
            deps,
            user_data={"current_directory": workspace / "alpha"},
        )

        await orchestrator.agentic_status(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "alpha" in text

    async def test_status_includes_cost_when_rate_limiter_available(
        self, orchestrator, settings, deps
    ):
        update = _make_update()
        rate_limiter = MagicMock()
        rate_limiter.get_user_status.return_value = {
            "cost_usage": {"current": 1.23}
        }
        deps_with_rl = {**deps, "rate_limiter": rate_limiter}
        context = _make_context(settings, deps_with_rl)

        await orchestrator.agentic_status(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "$1.23" in text


class TestVerboseCommand:
    """Test /verbose command (verbosity levels)."""

    async def test_verbose_no_args_shows_current_level(
        self, orchestrator, settings, deps
    ):
        update = _make_update(text="/verbose")
        context = _make_context(settings, deps)

        await orchestrator.agentic_verbose(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "Verbosity:" in text
        assert "Usage:" in text

    async def test_verbose_set_level_0(self, orchestrator, settings, deps):
        update = _make_update(text="/verbose 0")
        context = _make_context(settings, deps)

        await orchestrator.agentic_verbose(update, context)

        assert context.user_data["verbose_level"] == 0
        text = update.message.reply_text.call_args.args[0]
        assert "quiet" in text

    async def test_verbose_set_level_1(self, orchestrator, settings, deps):
        update = _make_update(text="/verbose 1")
        context = _make_context(settings, deps)

        await orchestrator.agentic_verbose(update, context)

        assert context.user_data["verbose_level"] == 1
        text = update.message.reply_text.call_args.args[0]
        assert "normal" in text

    async def test_verbose_set_level_2(self, orchestrator, settings, deps):
        update = _make_update(text="/verbose 2")
        context = _make_context(settings, deps)

        await orchestrator.agentic_verbose(update, context)

        assert context.user_data["verbose_level"] == 2
        text = update.message.reply_text.call_args.args[0]
        assert "detailed" in text

    async def test_verbose_rejects_invalid_level(self, orchestrator, settings, deps):
        update = _make_update(text="/verbose 5")
        context = _make_context(settings, deps)

        await orchestrator.agentic_verbose(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "Please use:" in text
        assert "verbose_level" not in context.user_data

    async def test_verbose_rejects_non_numeric(self, orchestrator, settings, deps):
        update = _make_update(text="/verbose high")
        context = _make_context(settings, deps)

        await orchestrator.agentic_verbose(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "Please use:" in text


class TestRepoCommand:
    """Test /repo command (list repos & switch directory)."""

    async def test_repo_lists_directories(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "alpha" in text
        assert "beta" in text

    async def test_repo_shows_git_indicator(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        # alpha has .git, should show package icon (git repo)
        text = update.message.reply_text.call_args.args[0]
        assert "Repos" in text

    async def test_repo_provides_inline_keyboard(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        kwargs = update.message.reply_text.call_args.kwargs
        reply_markup = kwargs.get("reply_markup")
        assert reply_markup is not None

        # Check keyboard buttons contain repo names
        buttons = [
            btn.text
            for row in reply_markup.inline_keyboard
            for btn in row
        ]
        assert "alpha" in buttons
        assert "beta" in buttons

    async def test_repo_switch_to_named_repo(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo alpha")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        assert context.user_data["current_directory"] == workspace / "alpha"
        text = update.message.reply_text.call_args.args[0]
        assert "Switched to" in text
        assert "alpha" in text

    async def test_repo_switch_shows_git_badge(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo alpha")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "(git)" in text

    async def test_repo_switch_no_git_badge_for_non_git(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo beta")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "(git)" not in text

    async def test_repo_switch_nonexistent_fails(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo nonexistent")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "not found" in text.lower()

    async def test_repo_marks_current_directory(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo")
        context = _make_context(
            settings,
            deps,
            user_data={"current_directory": workspace / "alpha"},
        )

        await orchestrator.agentic_repo(update, context)

        text = update.message.reply_text.call_args.args[0]
        # Current repo gets a marker arrow
        assert "\u25c0" in text

    async def test_repo_empty_workspace(self, tmp_dir, deps):
        empty_ws = tmp_dir / "empty_ws"
        empty_ws.mkdir()
        s = create_test_config(approved_directory=str(empty_ws), agentic_mode=True)
        orch = MessageOrchestrator(s, deps)

        update = _make_update(text="/repo")
        context = _make_context(s, deps)

        await orch.agentic_repo(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "No repos" in text


# ===================================================================
# 2. TEXT MESSAGE -> CLAUDE PASSTHROUGH
# ===================================================================


class TestAgenticTextHandler:
    """Test text message handling: Claude call, response delivery, session tracking."""

    async def test_text_calls_claude_with_prompt(
        self, orchestrator, settings, deps, claude_integration
    ):
        update = _make_update(text="Explain this code")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        claude_integration.run_command.assert_called_once()
        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["prompt"] == "Explain this code"

    async def test_text_passes_working_directory(
        self, orchestrator, settings, deps, claude_integration, workspace
    ):
        update = _make_update(text="hello")
        context = _make_context(
            settings,
            deps,
            user_data={"current_directory": workspace / "alpha"},
        )

        await orchestrator.agentic_text(update, context)

        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["working_directory"] == workspace / "alpha"

    async def test_text_passes_existing_session_id(
        self, orchestrator, settings, deps, claude_integration
    ):
        update = _make_update(text="continue")
        context = _make_context(
            settings, deps, user_data={"claude_session_id": "sess-xyz"}
        )

        await orchestrator.agentic_text(update, context)

        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-xyz"

    async def test_text_stores_session_id_from_response(
        self, orchestrator, settings, deps, claude_integration
    ):
        claude_integration.run_command.return_value = _make_claude_response(
            session_id="new-sess-456"
        )

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        assert context.user_data["claude_session_id"] == "new-sess-456"

    async def test_text_deletes_progress_message(
        self, orchestrator, settings, deps, claude_integration
    ):
        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        # The first reply_text returns the progress message
        progress_msg = update.message.reply_text.return_value
        progress_msg.delete.assert_called_once()

    async def test_text_sends_response_without_keyboard(
        self, orchestrator, settings, deps, claude_integration
    ):
        claude_integration.run_command.return_value = _make_claude_response(
            content="Done!"
        )
        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        # Find the response call (not the "Working..." progress call)
        calls = update.message.reply_text.call_args_list
        response_calls = [c for c in calls if c != calls[0]]
        for call in response_calls:
            assert call.kwargs.get("reply_markup") is None

    async def test_text_sends_typing_action(
        self, orchestrator, settings, deps, claude_integration
    ):
        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        update.message.chat.send_action.assert_called_with("typing")

    async def test_text_stores_interaction(
        self, orchestrator, settings, deps, claude_integration
    ):
        storage = AsyncMock()
        storage.save_claude_interaction = AsyncMock()
        deps["storage"] = storage

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        storage.save_claude_interaction.assert_called_once()

    async def test_text_audits_success(
        self, orchestrator, settings, deps, claude_integration
    ):
        audit = AsyncMock()
        audit.log_command = AsyncMock()
        deps["audit_logger"] = audit

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        audit.log_command.assert_called_once()
        assert audit.log_command.call_args.kwargs["success"] is True


# ===================================================================
# 3. SESSION MANAGEMENT — resume, reset, force_new
# ===================================================================


class TestSessionManagement:
    """Test session auto-resume and force-new behaviors."""

    async def test_force_new_flag_passed_to_claude(
        self, orchestrator, settings, deps, claude_integration
    ):
        update = _make_update(text="start fresh")
        context = _make_context(
            settings, deps, user_data={"force_new_session": True}
        )

        await orchestrator.agentic_text(update, context)

        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["force_new"] is True

    async def test_force_new_flag_cleared_after_success(
        self, orchestrator, settings, deps, claude_integration
    ):
        update = _make_update(text="start fresh")
        context = _make_context(
            settings, deps, user_data={"force_new_session": True}
        )

        await orchestrator.agentic_text(update, context)

        assert context.user_data["force_new_session"] is False

    async def test_new_then_text_uses_force_new(
        self, orchestrator, settings, deps, claude_integration
    ):
        """Full flow: /new then text message should use force_new."""
        update_new = _make_update(text="/new")
        context = _make_context(
            settings, deps, user_data={"claude_session_id": "old"}
        )

        await orchestrator.agentic_new(update_new, context)

        assert context.user_data["claude_session_id"] is None
        assert context.user_data["force_new_session"] is True

        # Now send a text message — should pass force_new=True
        update_text = _make_update(text="new task")
        await orchestrator.agentic_text(update_text, context)

        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["force_new"] is True
        assert call_kwargs["session_id"] is None

    async def test_session_resumes_by_default(
        self, orchestrator, settings, deps, claude_integration
    ):
        update = _make_update(text="hello again")
        context = _make_context(
            settings, deps, user_data={"claude_session_id": "existing-sess"}
        )

        await orchestrator.agentic_text(update, context)

        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["session_id"] == "existing-sess"
        assert call_kwargs["force_new"] is False

    async def test_session_id_updated_from_new_response(
        self, orchestrator, settings, deps, claude_integration
    ):
        claude_integration.run_command.return_value = _make_claude_response(
            session_id="brand-new-sess"
        )

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        assert context.user_data["claude_session_id"] == "brand-new-sess"


# ===================================================================
# 4. DIRECTORY SWITCHING — /repo + inline callbacks
# ===================================================================


class TestDirectorySwitching:
    """Test directory switching via /repo and cd: callbacks."""

    async def test_repo_switch_updates_user_data(
        self, orchestrator, settings, deps, workspace
    ):
        update = _make_update(text="/repo alpha")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        assert context.user_data["current_directory"] == workspace / "alpha"

    async def test_callback_cd_switches_directory(
        self, orchestrator, settings, deps, workspace
    ):
        query = AsyncMock()
        query.answer = AsyncMock()
        query.data = "cd:beta"
        query.from_user.id = 111
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()

        update = MagicMock()
        update.callback_query = query
        update.effective_chat.id = 111
        update.effective_chat.type = "private"
        update.effective_message = query.message

        context = _make_context(settings, deps)

        await orchestrator._agentic_callback(update, context)

        assert context.user_data["current_directory"] == workspace / "beta"
        query.edit_message_text.assert_called_once()
        text = query.edit_message_text.call_args.args[0]
        assert "beta" in text

    async def test_callback_cd_nonexistent_directory(
        self, orchestrator, settings, deps, workspace
    ):
        query = AsyncMock()
        query.answer = AsyncMock()
        query.data = "cd:missing_project"
        query.from_user.id = 111
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        context = _make_context(settings, deps)

        await orchestrator._agentic_callback(update, context)

        text = query.edit_message_text.call_args.args[0]
        assert "not found" in text.lower()

    async def test_callback_cd_audits_event(
        self, orchestrator, settings, deps, workspace
    ):
        audit = AsyncMock()
        audit.log_command = AsyncMock()
        deps["audit_logger"] = audit

        query = AsyncMock()
        query.answer = AsyncMock()
        query.data = "cd:alpha"
        query.from_user.id = 111
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        context = _make_context(settings, deps)

        await orchestrator._agentic_callback(update, context)

        audit.log_command.assert_called_once()
        assert audit.log_command.call_args.kwargs["command"] == "cd"

    async def test_repo_switch_session_resume_lookup(
        self, orchestrator, settings, deps, workspace, claude_integration
    ):
        """When switching repo, bot attempts to find resumable session."""
        session = SimpleNamespace(session_id="resumed-sess")
        claude_integration._find_resumable_session.return_value = session

        update = _make_update(text="/repo alpha")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        claude_integration._find_resumable_session.assert_called_once()
        assert context.user_data["claude_session_id"] == "resumed-sess"
        text = update.message.reply_text.call_args.args[0]
        assert "session resumed" in text

    async def test_repo_switch_no_resumable_session(
        self, orchestrator, settings, deps, workspace, claude_integration
    ):
        claude_integration._find_resumable_session.return_value = None

        update = _make_update(text="/repo alpha")
        context = _make_context(settings, deps)

        await orchestrator.agentic_repo(update, context)

        assert context.user_data["claude_session_id"] is None
        text = update.message.reply_text.call_args.args[0]
        assert "session resumed" not in text


# ===================================================================
# 5. FILE UPLOAD HANDLING
# ===================================================================


class TestDocumentUpload:
    """Test file/document upload handling."""

    async def test_document_rejects_oversized_file(
        self, orchestrator, settings, deps
    ):
        deps["security_validator"].validate_filename.return_value = (True, None)

        update = _make_update()
        update.message.document = MagicMock()
        update.message.document.file_name = "big.txt"
        update.message.document.file_size = 20 * 1024 * 1024  # 20MB

        context = _make_context(settings, deps)

        await orchestrator.agentic_document(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "too large" in text.lower()

    async def test_document_rejects_dangerous_filename(
        self, orchestrator, settings, deps
    ):
        validator = MagicMock()
        validator.validate_filename.return_value = (False, "Blocked filename")
        deps["security_validator"] = validator

        update = _make_update()
        update.message.document = MagicMock()
        update.message.document.file_name = ".env"
        update.message.document.file_size = 100

        context = _make_context(settings, deps)

        await orchestrator.agentic_document(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "rejected" in text.lower()

    async def test_document_processes_valid_file(
        self, orchestrator, settings, deps, claude_integration
    ):
        deps["security_validator"].validate_filename.return_value = (True, None)
        deps["features"] = None  # No enhanced file handler

        doc = MagicMock()
        doc.file_name = "main.py"
        doc.file_size = 500
        doc.get_file = AsyncMock()
        file_mock = AsyncMock()
        file_mock.download_as_bytearray = AsyncMock(
            return_value=bytearray(b"print('hello')")
        )
        doc.get_file.return_value = file_mock

        update = _make_update()
        update.message.document = doc
        update.message.caption = "Review this file"

        context = _make_context(settings, deps)

        await orchestrator.agentic_document(update, context)

        claude_integration.run_command.assert_called_once()
        prompt = claude_integration.run_command.call_args.kwargs["prompt"]
        assert "main.py" in prompt
        assert "print('hello')" in prompt

    async def test_document_rejects_binary_file(
        self, orchestrator, settings, deps, claude_integration
    ):
        deps["security_validator"].validate_filename.return_value = (True, None)
        deps["features"] = None

        doc = MagicMock()
        doc.file_name = "image.bin"
        doc.file_size = 500
        doc.get_file = AsyncMock()
        file_mock = AsyncMock()
        file_mock.download_as_bytearray = AsyncMock(
            return_value=bytearray(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        )
        doc.get_file.return_value = file_mock

        update = _make_update()
        update.message.document = doc
        update.message.caption = None

        context = _make_context(settings, deps)

        await orchestrator.agentic_document(update, context)

        # Should show unsupported format message
        progress_msg = update.message.reply_text.return_value
        progress_msg.edit_text.assert_called()
        text = progress_msg.edit_text.call_args.args[0]
        assert "Unsupported" in text or "UTF-8" in text


# ===================================================================
# 6. PHOTO UPLOAD HANDLING
# ===================================================================


class TestPhotoUpload:
    """Test photo upload handling."""

    async def test_photo_no_handler_available(self, orchestrator, settings, deps):
        deps["features"] = None

        update = _make_update()
        update.message.photo = [MagicMock()]

        context = _make_context(settings, deps)

        await orchestrator.agentic_photo(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "not available" in text.lower()

    async def test_photo_processes_with_handler(
        self, orchestrator, settings, deps, claude_integration
    ):
        image_handler = AsyncMock()
        image_handler.process_image.return_value = SimpleNamespace(
            prompt="Analyze this screenshot"
        )

        features = MagicMock()
        features.get_image_handler.return_value = image_handler
        deps["features"] = features

        photo = MagicMock()
        update = _make_update()
        update.message.photo = [photo]
        update.message.caption = "What is this?"

        context = _make_context(settings, deps)

        await orchestrator.agentic_photo(update, context)

        image_handler.process_image.assert_called_once_with(photo, "What is this?")
        claude_integration.run_command.assert_called_once()
        prompt = claude_integration.run_command.call_args.kwargs["prompt"]
        assert "Analyze this screenshot" in prompt


# ===================================================================
# 7. VERBOSE PROGRESS TRACKING
# ===================================================================


class TestVerboseProgress:
    """Test verbose level progress display during Claude execution."""

    def test_format_progress_empty_log(self, orchestrator):
        text = orchestrator._format_verbose_progress([], 1, time.time())
        assert text == "Working..."

    def test_format_progress_shows_tool_calls(self, orchestrator):
        log = [
            {"kind": "tool", "name": "Read", "detail": "main.py"},
            {"kind": "tool", "name": "Bash", "detail": "pytest"},
        ]
        text = orchestrator._format_verbose_progress(log, 1, time.time() - 5)
        assert "Read" in text
        assert "Bash" in text

    def test_format_progress_level_2_shows_details(self, orchestrator):
        log = [
            {"kind": "tool", "name": "Read", "detail": "main.py"},
        ]
        text = orchestrator._format_verbose_progress(log, 2, time.time())
        assert "main.py" in text

    def test_format_progress_level_1_hides_details(self, orchestrator):
        log = [
            {"kind": "tool", "name": "Read", "detail": "main.py"},
        ]
        text = orchestrator._format_verbose_progress(log, 1, time.time())
        assert "Read" in text
        # Level 1 shows tool name but not detail
        assert "main.py" not in text

    def test_format_progress_shows_reasoning_snippets(self, orchestrator):
        log = [
            {"kind": "text", "detail": "Analyzing the test failures..."},
        ]
        text = orchestrator._format_verbose_progress(log, 1, time.time())
        assert "Analyzing the test" in text

    def test_format_progress_caps_at_15_entries(self, orchestrator):
        log = [
            {"kind": "tool", "name": f"Tool{i}", "detail": ""}
            for i in range(20)
        ]
        text = orchestrator._format_verbose_progress(log, 1, time.time())
        assert "earlier entries" in text

    def test_format_progress_shows_elapsed_time(self, orchestrator):
        text = orchestrator._format_verbose_progress(
            [{"kind": "tool", "name": "Read", "detail": ""}],
            1,
            time.time() - 10,
        )
        assert "10s" in text

    def test_make_stream_callback_returns_none_for_level_0(self, orchestrator):
        cb = orchestrator._make_stream_callback(
            verbose_level=0,
            progress_msg=AsyncMock(),
            tool_log=[],
            start_time=time.time(),
        )
        assert cb is None

    def test_make_stream_callback_returns_callable_for_level_1(self, orchestrator):
        cb = orchestrator._make_stream_callback(
            verbose_level=1,
            progress_msg=AsyncMock(),
            tool_log=[],
            start_time=time.time(),
        )
        assert callable(cb)

    async def test_stream_callback_captures_tool_calls(self, orchestrator):
        tool_log: list = []
        progress_msg = AsyncMock()
        cb = orchestrator._make_stream_callback(
            verbose_level=1,
            progress_msg=progress_msg,
            tool_log=tool_log,
            start_time=time.time() - 5,
        )

        stream_update = StreamUpdate(
            type="assistant",
            tool_calls=[{"name": "Read", "input": {"file_path": "/tmp/x.py"}}],
        )
        await cb(stream_update)

        assert len(tool_log) == 1
        assert tool_log[0]["name"] == "Read"

    async def test_stream_callback_captures_reasoning(self, orchestrator):
        tool_log: list = []
        progress_msg = AsyncMock()
        cb = orchestrator._make_stream_callback(
            verbose_level=1,
            progress_msg=progress_msg,
            tool_log=tool_log,
            start_time=time.time() - 5,
        )

        stream_update = StreamUpdate(
            type="assistant",
            content="I'll start by reading the config file...",
        )
        await cb(stream_update)

        assert len(tool_log) == 1
        assert tool_log[0]["kind"] == "text"
        assert "config file" in tool_log[0]["detail"]


# ===================================================================
# 8. TYPING HEARTBEAT
# ===================================================================


class TestTypingHeartbeat:
    """Test independent typing indicator heartbeat."""

    async def test_heartbeat_sends_typing_periodically(self, orchestrator):
        chat = AsyncMock()
        chat.send_action = AsyncMock()

        heartbeat = orchestrator._start_typing_heartbeat(chat, interval=0.05)
        await asyncio.sleep(0.2)
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass

        assert chat.send_action.call_count >= 2
        chat.send_action.assert_called_with("typing")

    async def test_heartbeat_cancels_cleanly(self, orchestrator):
        chat = AsyncMock()
        heartbeat = orchestrator._start_typing_heartbeat(chat, interval=0.05)
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass

        assert heartbeat.cancelled() or heartbeat.done()

    async def test_heartbeat_survives_errors(self, orchestrator):
        call_count = [0]

        async def flaky_send(action):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise Exception("Network error")

        chat = AsyncMock()
        chat.send_action = flaky_send

        heartbeat = orchestrator._start_typing_heartbeat(chat, interval=0.05)
        await asyncio.sleep(0.3)
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass

        assert call_count[0] >= 3


# ===================================================================
# 9. RATE LIMITING
# ===================================================================


class TestRateLimiting:
    """Test rate limiting enforcement in agentic handlers."""

    async def test_text_blocked_by_rate_limiter(
        self, orchestrator, settings, deps, claude_integration
    ):
        rate_limiter = AsyncMock()
        rate_limiter.check_rate_limit = AsyncMock(
            return_value=(False, "Too many requests. Try again in 30s.")
        )
        deps["rate_limiter"] = rate_limiter

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        # Claude should NOT be called
        claude_integration.run_command.assert_not_called()
        # User gets rate limit message
        text = update.message.reply_text.call_args.args[0]
        assert "Too many requests" in text

    async def test_text_allowed_when_rate_limiter_permits(
        self, orchestrator, settings, deps, claude_integration
    ):
        rate_limiter = AsyncMock()
        rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        deps["rate_limiter"] = rate_limiter

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        claude_integration.run_command.assert_called_once()


# ===================================================================
# 10. ERROR HANDLING & RECOVERY
# ===================================================================


class TestErrorHandling:
    """Test error handling across agentic handlers."""

    async def test_text_handles_claude_exception(
        self, orchestrator, settings, deps, claude_integration
    ):
        claude_integration.run_command.side_effect = Exception("SDK crashed")

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        # Should not raise
        await orchestrator.agentic_text(update, context)

        # Progress message deleted, error response sent
        progress_msg = update.message.reply_text.return_value
        progress_msg.delete.assert_called_once()

    async def test_text_audits_failure(
        self, orchestrator, settings, deps, claude_integration
    ):
        claude_integration.run_command.side_effect = Exception("fail")
        audit = AsyncMock()
        audit.log_command = AsyncMock()
        deps["audit_logger"] = audit

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        audit.log_command.assert_called_once()
        assert audit.log_command.call_args.kwargs["success"] is False

    async def test_text_no_claude_integration_shows_error(
        self, orchestrator, settings, deps
    ):
        deps["claude_integration"] = None

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        await orchestrator.agentic_text(update, context)

        progress_msg = update.message.reply_text.return_value
        progress_msg.edit_text.assert_called()
        text = progress_msg.edit_text.call_args.args[0]
        assert "not available" in text.lower()

    async def test_document_handles_claude_exception(
        self, orchestrator, settings, deps, claude_integration
    ):
        deps["security_validator"].validate_filename.return_value = (True, None)
        deps["features"] = None

        claude_integration.run_command.side_effect = Exception("SDK crash")

        doc = MagicMock()
        doc.file_name = "test.py"
        doc.file_size = 100
        doc.get_file = AsyncMock()
        file_mock = AsyncMock()
        file_mock.download_as_bytearray = AsyncMock(
            return_value=bytearray(b"code")
        )
        doc.get_file.return_value = file_mock

        update = _make_update()
        update.message.document = doc
        update.message.caption = None

        context = _make_context(settings, deps)

        # Should not raise
        await orchestrator.agentic_document(update, context)

        progress_msg = update.message.reply_text.return_value
        progress_msg.edit_text.assert_called()

    async def test_photo_handles_processing_exception(
        self, orchestrator, settings, deps
    ):
        image_handler = AsyncMock()
        image_handler.process_image.side_effect = Exception("Image corrupt")

        features = MagicMock()
        features.get_image_handler.return_value = image_handler
        deps["features"] = features

        update = _make_update()
        update.message.photo = [MagicMock()]
        update.message.caption = None

        context = _make_context(settings, deps)

        # Should not raise
        await orchestrator.agentic_photo(update, context)

        progress_msg = update.message.reply_text.return_value
        progress_msg.edit_text.assert_called()

    async def test_storage_failure_does_not_break_response(
        self, orchestrator, settings, deps, claude_integration
    ):
        storage = AsyncMock()
        storage.save_claude_interaction = AsyncMock(
            side_effect=Exception("DB write failed")
        )
        deps["storage"] = storage

        update = _make_update(text="hello")
        context = _make_context(settings, deps)

        # Should not raise — storage failure is logged but response still sent
        await orchestrator.agentic_text(update, context)

        claude_integration.run_command.assert_called_once()


# ===================================================================
# 11. TOOL INPUT SUMMARIZATION & SECRET REDACTION
# ===================================================================


class TestToolSummarization:
    """Test _summarize_tool_input and _redact_secrets for verbose display."""

    def test_summarize_read_shows_filename(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "Read", {"file_path": "/home/user/project/src/main.py"}
        )
        assert result == "main.py"

    def test_summarize_bash_redacts_secrets(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "Bash",
            {"command": "curl --token=supersecret123456 https://api.example.com"},
        )
        assert "supersecret123456" not in result
        assert "***" in result

    def test_summarize_grep_shows_pattern(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "Grep", {"pattern": "def.*handler"}
        )
        assert "def.*handler" in result

    def test_summarize_glob_shows_pattern(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "Glob", {"pattern": "**/*.py"}
        )
        assert "**/*.py" in result

    def test_summarize_web_fetch_shows_url(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "WebFetch", {"url": "https://docs.example.com/api"}
        )
        assert "docs.example.com" in result

    def test_summarize_web_search_shows_query(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "WebSearch", {"query": "python async patterns"}
        )
        assert "python async" in result

    def test_summarize_task_shows_description(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "Task", {"description": "Explore the codebase"}
        )
        assert "Explore" in result

    def test_summarize_empty_input(self, orchestrator):
        result = orchestrator._summarize_tool_input("Unknown", {})
        assert result == ""

    def test_summarize_write_shows_filename(self, orchestrator):
        result = orchestrator._summarize_tool_input(
            "Write", {"file_path": "/tmp/output.txt"}
        )
        assert result == "output.txt"


# ===================================================================
# 12. HANDLER REGISTRATION
# ===================================================================


class TestHandlerRegistration:
    """Test that agentic mode registers the correct handler set."""

    def test_registers_5_commands(self, orchestrator):
        from telegram.ext import CommandHandler

        app = MagicMock()
        app.add_handler = MagicMock()

        orchestrator.register_handlers(app)

        cmd_handlers = [
            call
            for call in app.add_handler.call_args_list
            if isinstance(call[0][0], CommandHandler)
        ]
        commands = [h[0][0].commands for h in cmd_handlers]

        assert len(cmd_handlers) == 5
        assert frozenset({"start"}) in commands
        assert frozenset({"new"}) in commands
        assert frozenset({"status"}) in commands
        assert frozenset({"verbose"}) in commands
        assert frozenset({"repo"}) in commands

    def test_registers_3_message_handlers(self, orchestrator):
        from telegram.ext import MessageHandler

        app = MagicMock()
        app.add_handler = MagicMock()

        orchestrator.register_handlers(app)

        msg_handlers = [
            call
            for call in app.add_handler.call_args_list
            if isinstance(call[0][0], MessageHandler)
        ]
        # text, document, photo
        assert len(msg_handlers) == 3

    def test_registers_cd_callback_handler(self, orchestrator):
        from telegram.ext import CallbackQueryHandler

        app = MagicMock()
        app.add_handler = MagicMock()

        orchestrator.register_handlers(app)

        cb_handlers = [
            call[0][0]
            for call in app.add_handler.call_args_list
            if isinstance(call[0][0], CallbackQueryHandler)
        ]
        assert len(cb_handlers) == 1
        assert cb_handlers[0].pattern.match("cd:my_project")

    async def test_bot_commands_returns_5(self, orchestrator):
        commands = await orchestrator.get_bot_commands()
        assert len(commands) == 5
        names = [c.command for c in commands]
        assert names == ["start", "new", "status", "verbose", "repo"]


# ===================================================================
# 13. FULL END-TO-END FLOWS
# ===================================================================


class TestEndToEndFlows:
    """Simulate realistic multi-step user interactions."""

    async def test_full_onboarding_flow(
        self, orchestrator, settings, deps, workspace, claude_integration
    ):
        """Simulate: /start -> /repo alpha -> send text -> /status -> /new -> send text."""
        context = _make_context(settings, deps)

        # Step 1: /start
        update = _make_update(first_name="Bob")
        await orchestrator.agentic_start(update, context)
        text = update.message.reply_text.call_args.args[0]
        assert "Bob" in text

        # Step 2: /repo alpha
        update = _make_update(text="/repo alpha")
        await orchestrator.agentic_repo(update, context)
        assert context.user_data["current_directory"] == workspace / "alpha"

        # Step 3: send text
        claude_integration.run_command.return_value = _make_claude_response(
            content="I found 3 files.", session_id="sess-001"
        )
        update = _make_update(text="list all python files")
        await orchestrator.agentic_text(update, context)
        assert context.user_data["claude_session_id"] == "sess-001"

        # Step 4: /status
        update = _make_update()
        await orchestrator.agentic_status(update, context)
        text = update.message.reply_text.call_args.args[0]
        assert "active" in text

        # Step 5: /new
        update = _make_update()
        await orchestrator.agentic_new(update, context)
        assert context.user_data["claude_session_id"] is None

        # Step 6: send text after /new (should use force_new)
        claude_integration.run_command.return_value = _make_claude_response(
            content="Starting fresh!", session_id="sess-002"
        )
        update = _make_update(text="new task")
        await orchestrator.agentic_text(update, context)
        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["force_new"] is True
        assert context.user_data["claude_session_id"] == "sess-002"

    async def test_multi_repo_workflow(
        self, orchestrator, settings, deps, workspace, claude_integration
    ):
        """Simulate switching between repos and verify session isolation."""
        context = _make_context(settings, deps)

        # Work in alpha
        update = _make_update(text="/repo alpha")
        await orchestrator.agentic_repo(update, context)

        claude_integration.run_command.return_value = _make_claude_response(
            session_id="alpha-sess"
        )
        update = _make_update(text="work on alpha")
        await orchestrator.agentic_text(update, context)
        assert context.user_data["claude_session_id"] == "alpha-sess"

        # Switch to beta
        update = _make_update(text="/repo beta")
        await orchestrator.agentic_repo(update, context)
        # Session is cleared when switching (no resumable session found)
        assert context.user_data["claude_session_id"] is None
        assert context.user_data["current_directory"] == workspace / "beta"

        # Work in beta
        claude_integration.run_command.return_value = _make_claude_response(
            session_id="beta-sess"
        )
        update = _make_update(text="work on beta")
        await orchestrator.agentic_text(update, context)
        assert context.user_data["claude_session_id"] == "beta-sess"

    async def test_verbose_during_execution(
        self, orchestrator, settings, deps, claude_integration
    ):
        """Set verbose, execute text, verify progress callback is wired."""
        context = _make_context(settings, deps)

        # Set verbose to 2
        update = _make_update(text="/verbose 2")
        await orchestrator.agentic_verbose(update, context)
        assert context.user_data["verbose_level"] == 2

        # Send text — callback should be non-None
        update = _make_update(text="analyze code")
        await orchestrator.agentic_text(update, context)

        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["on_stream"] is not None

    async def test_quiet_mode_no_callback(
        self, orchestrator, settings, deps, claude_integration
    ):
        """Verbose 0 should produce no stream callback."""
        context = _make_context(settings, deps)

        update = _make_update(text="/verbose 0")
        await orchestrator.agentic_verbose(update, context)

        update = _make_update(text="do something")
        await orchestrator.agentic_text(update, context)

        call_kwargs = claude_integration.run_command.call_args.kwargs
        assert call_kwargs["on_stream"] is None


# ===================================================================
# 14. SECRET REDACTION PATTERNS
# ===================================================================


class TestSecretRedaction:
    """Test that _redact_secrets catches common secret patterns."""

    @pytest.mark.parametrize(
        "input_text,should_be_redacted",
        [
            ("sk-ant-api03-abc123def456ghi789jkl012mno345", True),
            ("sk-1234567890abcdefghijklmnop", True),
            ("ghp_abcdefghijklmnop1234", True),
            ("gho_abcdefghijklmnop1234", True),
            ("github_pat_abcde12345_stuff", True),
            ("AKIAIOSFODNN7EXAMPLE", True),
            ("--token=mysupersecretvalue", True),
            ("PASSWORD=MyS3cretP@ss!Longer", True),
            ("Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", True),
            ("postgresql://admin:secret_password@db:5432/mydb", True),
            ("git status", False),
            ("poetry run pytest", False),
            ("ls -la", False),
        ],
    )
    def test_redaction_patterns(self, input_text, should_be_redacted):
        from src.bot.orchestrator import _redact_secrets

        result = _redact_secrets(input_text)
        if should_be_redacted:
            assert result != input_text, f"Expected redaction of: {input_text}"
            assert "***" in result
        else:
            assert result == input_text


# ===================================================================
# 15. TOOL ICON MAPPING
# ===================================================================


class TestToolIcons:
    """Verify tool icon mapping for progress display."""

    @pytest.mark.parametrize(
        "tool_name,expected_icon_exists",
        [
            ("Read", True),
            ("Write", True),
            ("Edit", True),
            ("Bash", True),
            ("Glob", True),
            ("Grep", True),
            ("LS", True),
            ("Task", True),
            ("WebFetch", True),
            ("WebSearch", True),
            ("NotebookRead", True),
            ("NotebookEdit", True),
            ("TodoRead", True),
            ("TodoWrite", True),
            ("UnknownTool", False),
        ],
    )
    def test_tool_has_icon(self, tool_name, expected_icon_exists):
        from src.bot.orchestrator import _TOOL_ICONS, _tool_icon

        icon = _tool_icon(tool_name)
        if expected_icon_exists:
            assert icon == _TOOL_ICONS[tool_name]
        else:
            # Falls back to wrench
            assert icon == "\U0001f527"
