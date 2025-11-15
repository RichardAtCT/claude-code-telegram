"""Comprehensive tests for callback query handlers."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from telegram import CallbackQuery, InlineKeyboardMarkup, Message, Update, User

from src.bot.handlers.callback import (
    handle_action_callback,
    handle_callback_query,
    handle_cd_callback,
    handle_confirm_callback,
    handle_conversation_callback,
    handle_export_callback,
    handle_followup_callback,
    handle_git_callback,
    handle_quick_action_callback,
)
from src.config.settings import Settings


@pytest.fixture
def temp_approved_dir():
    """Create temporary approved directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        approved_dir = Path(temp_dir) / "approved"
        approved_dir.mkdir()
        # Create test structure
        (approved_dir / "project1").mkdir()
        (approved_dir / "project2").mkdir()
        (approved_dir / ".git").mkdir()  # For git tests
        (approved_dir / "test.py").write_text("print('hello')")
        yield approved_dir


@pytest.fixture
def mock_settings(temp_approved_dir):
    """Create mock settings."""
    settings = Mock(spec=Settings)
    settings.approved_directory = temp_approved_dir
    settings.claude_max_cost_per_user = 10.0
    settings.enable_quick_actions = True
    return settings


@pytest.fixture
def mock_callback_query():
    """Create mock callback query."""
    query = AsyncMock(spec=CallbackQuery)
    query.from_user = Mock(spec=User)
    query.from_user.id = 123456789
    query.data = "action:help"
    query.message = AsyncMock(spec=Message)
    query.message.message_id = 1
    return query


@pytest.fixture
def mock_context(mock_settings):
    """Create mock context."""
    context = AsyncMock()
    context.bot_data = {
        "settings": mock_settings,
        "audit_logger": AsyncMock(),
        "security_validator": AsyncMock(),
        "rate_limiter": AsyncMock(),
        "claude_integration": AsyncMock(),
        "features": AsyncMock(),
    }
    context.user_data = {}
    return context


class TestHandleCallbackQuery:
    """Tests for main callback query router."""

    @pytest.mark.asyncio
    async def test_callback_query_routing_cd(self, mock_callback_query, mock_context):
        """Test routing to cd handler."""
        mock_callback_query.data = "cd:project1"

        with patch("src.bot.handlers.callback.handle_cd_callback") as mock_handler:
            mock_handler.return_value = AsyncMock()
            await handle_callback_query(
                Mock(callback_query=mock_callback_query), mock_context
            )

            # Verify handler was called
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_query_routing_action(self, mock_callback_query, mock_context):
        """Test routing to action handler."""
        mock_callback_query.data = "action:help"

        with patch("src.bot.handlers.callback.handle_action_callback") as mock_handler:
            mock_handler.return_value = AsyncMock()
            await handle_callback_query(
                Mock(callback_query=mock_callback_query), mock_context
            )

            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_query_unknown_action(
        self, mock_callback_query, mock_context
    ):
        """Test handling unknown action."""
        mock_callback_query.data = "unknown:action"

        update = Mock(callback_query=mock_callback_query)
        await handle_callback_query(update, mock_context)

        # Verify unknown action message
        mock_callback_query.edit_message_text.assert_called_once()
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Unknown Action" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_callback_query_error_handling(
        self, mock_callback_query, mock_context
    ):
        """Test error handling in callback routing."""
        mock_callback_query.data = "action:help"

        with patch(
            "src.bot.handlers.callback.handle_action_callback",
            side_effect=Exception("Test error"),
        ):
            update = Mock(callback_query=mock_callback_query)
            await handle_callback_query(update, mock_context)

            # Verify error message
            assert mock_callback_query.edit_message_text.call_count >= 1

    @pytest.mark.asyncio
    async def test_callback_query_answer_called(
        self, mock_callback_query, mock_context
    ):
        """Test that callback is acknowledged."""
        update = Mock(callback_query=mock_callback_query)
        await handle_callback_query(update, mock_context)

        # Verify answer was called
        mock_callback_query.answer.assert_called_once()


class TestHandleCdCallback:
    """Tests for directory change callback."""

    @pytest.mark.asyncio
    async def test_cd_callback_to_project(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test changing to project directory."""
        # Mock security validator
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path.return_value = (
            True,
            temp_approved_dir / "project1",
            None,
        )

        await handle_cd_callback(mock_callback_query, "project1", mock_context)

        # Verify directory changed
        assert mock_context.user_data["current_directory"] == temp_approved_dir / "project1"
        # Verify session cleared
        assert mock_context.user_data.get("claude_session_id") is None

        # Verify success message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Directory Changed" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cd_callback_to_root(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test changing to root directory."""
        await handle_cd_callback(mock_callback_query, "/", mock_context)

        # Verify at root
        assert mock_context.user_data["current_directory"] == temp_approved_dir

    @pytest.mark.asyncio
    async def test_cd_callback_to_parent(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test navigating to parent directory."""
        # Start in subdirectory
        mock_context.user_data["current_directory"] = temp_approved_dir / "project1"

        await handle_cd_callback(mock_callback_query, "..", mock_context)

        # Verify at parent
        assert mock_context.user_data["current_directory"] == temp_approved_dir

    @pytest.mark.asyncio
    async def test_cd_callback_security_blocked(self, mock_callback_query, mock_context):
        """Test security validation blocks malicious path."""
        # Mock security validator to reject
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path.return_value = (
            False,
            None,
            "Path traversal detected",
        )

        await handle_cd_callback(mock_callback_query, "../../../etc", mock_context)

        # Verify access denied message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Access Denied" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cd_callback_nonexistent_directory(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test changing to nonexistent directory."""
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path.return_value = (
            True,
            temp_approved_dir / "nonexistent",
            None,
        )

        await handle_cd_callback(mock_callback_query, "nonexistent", mock_context)

        # Verify not found message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Not Found" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cd_callback_audit_logging(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test that directory change is logged."""
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path.return_value = (
            True,
            temp_approved_dir / "project1",
            None,
        )

        await handle_cd_callback(mock_callback_query, "project1", mock_context)

        # Verify audit log
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_command.assert_called_with(
            user_id=123456789, command="cd", args=["project1"], success=True
        )


class TestHandleActionCallback:
    """Tests for action callback routing."""

    @pytest.mark.asyncio
    async def test_action_help(self, mock_callback_query, mock_context):
        """Test help action."""
        await handle_action_callback(mock_callback_query, "help", mock_context)

        # Verify help message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Quick Help" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_action_show_projects(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test show projects action."""
        await handle_action_callback(mock_callback_query, "show_projects", mock_context)

        # Verify projects shown
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Available Projects" in call_args[0][0]
        assert "project1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_action_new_session(self, mock_callback_query, mock_context):
        """Test new session action."""
        await handle_action_callback(mock_callback_query, "new_session", mock_context)

        # Verify session cleared
        assert mock_context.user_data.get("claude_session_id") is None
        assert mock_context.user_data.get("session_started") is True

        # Verify message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "New Claude Code Session" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_action_status(self, mock_callback_query, mock_context):
        """Test status action."""
        await handle_action_callback(mock_callback_query, "status", mock_context)

        # Verify status message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Session Status" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_action_ls(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test list files action."""
        await handle_action_callback(mock_callback_query, "ls", mock_context)

        # Verify file listing
        call_args = mock_callback_query.edit_message_text.call_args
        assert "project1" in call_args[0][0] or "project2" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_action_unknown(self, mock_callback_query, mock_context):
        """Test unknown action."""
        await handle_action_callback(mock_callback_query, "unknown_action", mock_context)

        # Verify unknown action message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Unknown Action" in call_args[0][0]


class TestHandleConfirmCallback:
    """Tests for confirmation callbacks."""

    @pytest.mark.asyncio
    async def test_confirm_yes(self, mock_callback_query, mock_context):
        """Test confirmation yes."""
        await handle_confirm_callback(mock_callback_query, "yes", mock_context)

        call_args = mock_callback_query.edit_message_text.call_args
        assert "Confirmed" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_confirm_no(self, mock_callback_query, mock_context):
        """Test confirmation no."""
        await handle_confirm_callback(mock_callback_query, "no", mock_context)

        call_args = mock_callback_query.edit_message_text.call_args
        assert "Cancelled" in call_args[0][0]


class TestHandleContinueAction:
    """Tests for continue session action."""

    @pytest.mark.asyncio
    async def test_continue_with_existing_session(
        self, mock_callback_query, mock_context, mock_settings
    ):
        """Test continuing existing session."""
        mock_context.user_data["claude_session_id"] = "existing_session"

        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = "existing_session"
        mock_response.content = "Continuing where we left off"
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        # Import and call the internal handler
        from src.bot.handlers.callback import _handle_continue_action

        await _handle_continue_action(mock_callback_query, mock_context)

        # Verify Claude was called
        mock_context.bot_data["claude_integration"].run_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_no_session(self, mock_callback_query, mock_context):
        """Test continue when no session found."""
        mock_context.bot_data["claude_integration"].continue_session.return_value = None

        from src.bot.handlers.callback import _handle_continue_action

        await _handle_continue_action(mock_callback_query, mock_context)

        # Verify no session message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "No Session Found" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_continue_no_integration(self, mock_callback_query, mock_context):
        """Test continue when integration not available."""
        mock_context.bot_data["claude_integration"] = None

        from src.bot.handlers.callback import _handle_continue_action

        await _handle_continue_action(mock_callback_query, mock_context)

        # Verify error message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Not Available" in call_args[0][0]


class TestHandleEndSessionAction:
    """Tests for end session action."""

    @pytest.mark.asyncio
    async def test_end_session_success(self, mock_callback_query, mock_context):
        """Test successful session end."""
        mock_context.user_data["claude_session_id"] = "active_session"

        from src.bot.handlers.callback import _handle_end_session_action

        await _handle_end_session_action(mock_callback_query, mock_context)

        # Verify session cleared
        assert mock_context.user_data.get("claude_session_id") is None
        assert mock_context.user_data.get("session_started") is False

        # Verify message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Session Ended" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_end_session_no_active(self, mock_callback_query, mock_context):
        """Test ending when no session active."""
        from src.bot.handlers.callback import _handle_end_session_action

        await _handle_end_session_action(mock_callback_query, mock_context)

        # Verify no session message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "No Active Session" in call_args[0][0]


class TestHandleQuickActionCallback:
    """Tests for quick action callbacks."""

    @pytest.mark.asyncio
    async def test_quick_action_not_available(self, mock_callback_query, mock_context):
        """Test quick action when not available."""
        mock_context.bot_data["quick_actions"] = None

        await handle_quick_action_callback(
            mock_callback_query, "test", mock_context
        )

        # Verify error message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Not Available" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_quick_action_no_integration(self, mock_callback_query, mock_context):
        """Test quick action when Claude integration not available."""
        mock_context.bot_data["quick_actions"] = Mock()
        mock_context.bot_data["claude_integration"] = None

        await handle_quick_action_callback(
            mock_callback_query, "test", mock_context
        )

        # Verify error message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Not Available" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_quick_action_success(
        self, mock_callback_query, mock_context, mock_settings
    ):
        """Test successful quick action execution."""
        # Mock quick actions
        mock_action = Mock()
        mock_action.icon = "🧪"
        mock_action.name = "Run Tests"
        mock_action.prompt = "Run all tests in this project"

        quick_actions = Mock()
        quick_actions.actions = {"test": mock_action}
        mock_context.bot_data["quick_actions"] = quick_actions

        # Mock Claude response
        mock_response = Mock()
        mock_response.content = "All tests passed!"
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        await handle_quick_action_callback(
            mock_callback_query, "test", mock_context
        )

        # Verify Claude was called
        mock_context.bot_data["claude_integration"].run_command.assert_called_once()

        # Verify response sent
        mock_callback_query.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_quick_action_not_found(self, mock_callback_query, mock_context):
        """Test quick action that doesn't exist."""
        quick_actions = Mock()
        quick_actions.actions = {}
        mock_context.bot_data["quick_actions"] = quick_actions

        await handle_quick_action_callback(
            mock_callback_query, "nonexistent", mock_context
        )

        # Verify not found message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Not Found" in call_args[0][0]


class TestHandleGitCallback:
    """Tests for git callback handlers."""

    @pytest.mark.asyncio
    async def test_git_disabled(self, mock_callback_query, mock_context):
        """Test git callback when disabled."""
        features = mock_context.bot_data["features"]
        features.is_enabled.return_value = False

        await handle_git_callback(mock_callback_query, "status", mock_context)

        # Verify disabled message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Disabled" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_status(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test git status callback."""
        features = mock_context.bot_data["features"]
        features.is_enabled.return_value = True

        # Mock git integration
        mock_git = AsyncMock()
        mock_status = Mock()
        mock_status.branch = "main"
        mock_status.ahead = 0
        mock_status.behind = 0
        mock_status.is_clean = True
        mock_status.modified = []
        mock_git.get_status.return_value = mock_status
        mock_git.format_status.return_value = "Git status: clean"
        features.get_git_integration.return_value = mock_git

        await handle_git_callback(mock_callback_query, "status", mock_context)

        # Verify status shown
        mock_git.get_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_git_diff(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test git diff callback."""
        features = mock_context.bot_data["features"]
        features.is_enabled.return_value = True

        # Mock git integration
        mock_git = AsyncMock()
        mock_git.get_diff.return_value = "diff --git a/test.py b/test.py"
        features.get_git_integration.return_value = mock_git

        await handle_git_callback(mock_callback_query, "diff", mock_context)

        # Verify diff shown
        mock_git.get_diff.assert_called_once()
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Git Diff" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_diff_empty(self, mock_callback_query, mock_context):
        """Test git diff when no changes."""
        features = mock_context.bot_data["features"]
        features.is_enabled.return_value = True

        mock_git = AsyncMock()
        mock_git.get_diff.return_value = ""
        features.get_git_integration.return_value = mock_git

        await handle_git_callback(mock_callback_query, "diff", mock_context)

        # Verify no changes message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "No changes" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_log(self, mock_callback_query, mock_context):
        """Test git log callback."""
        features = mock_context.bot_data["features"]
        features.is_enabled.return_value = True

        # Mock git integration
        mock_git = AsyncMock()
        mock_commit = Mock()
        mock_commit.hash = "abc123def456"
        mock_commit.message = "Initial commit"
        mock_git.get_file_history.return_value = [mock_commit]
        features.get_git_integration.return_value = mock_git

        await handle_git_callback(mock_callback_query, "log", mock_context)

        # Verify log shown
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Git Log" in call_args[0][0]
        assert "abc123d" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_unknown_action(self, mock_callback_query, mock_context):
        """Test unknown git action."""
        features = mock_context.bot_data["features"]
        features.is_enabled.return_value = True
        features.get_git_integration.return_value = AsyncMock()

        await handle_git_callback(mock_callback_query, "unknown", mock_context)

        # Verify unknown action message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Unknown Git Action" in call_args[0][0]


class TestHandleExportCallback:
    """Tests for export callback handlers."""

    @pytest.mark.asyncio
    async def test_export_cancel(self, mock_callback_query, mock_context):
        """Test export cancellation."""
        await handle_export_callback(mock_callback_query, "cancel", mock_context)

        # Verify cancelled message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Cancelled" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_export_not_available(self, mock_callback_query, mock_context):
        """Test export when not available."""
        mock_context.bot_data["features"] = None

        await handle_export_callback(mock_callback_query, "markdown", mock_context)

        # Verify unavailable message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Unavailable" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_export_no_session(self, mock_callback_query, mock_context):
        """Test export when no session."""
        features = mock_context.bot_data["features"]
        features.get_session_export.return_value = Mock()

        await handle_export_callback(mock_callback_query, "markdown", mock_context)

        # Verify no session message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "No Active Session" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_export_success(self, mock_callback_query, mock_context):
        """Test successful export."""
        mock_context.user_data["claude_session_id"] = "test_session"

        features = mock_context.bot_data["features"]
        mock_exporter = AsyncMock()

        # Mock export result
        from datetime import datetime

        mock_export = Mock()
        mock_export.content = "# Session Export\n\nContent here"
        mock_export.filename = "session_export.md"
        mock_export.format = "markdown"
        mock_export.size_bytes = 1024
        mock_export.created_at = datetime.now()
        mock_exporter.export_session.return_value = mock_export
        features.get_session_export.return_value = mock_exporter

        await handle_export_callback(mock_callback_query, "markdown", mock_context)

        # Verify export was called
        mock_exporter.export_session.assert_called_once()

        # Verify document was sent
        mock_callback_query.message.reply_document.assert_called_once()


class TestHandleFollowupCallback:
    """Tests for followup suggestion callbacks."""

    @pytest.mark.asyncio
    async def test_followup_not_available(self, mock_callback_query, mock_context):
        """Test followup when not available."""
        mock_context.bot_data["conversation_enhancer"] = None

        await handle_followup_callback(
            mock_callback_query, "suggestion_123", mock_context
        )

        # Verify not available message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Not Available" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_followup_success(self, mock_callback_query, mock_context):
        """Test successful followup handling."""
        mock_context.bot_data["conversation_enhancer"] = Mock()

        await handle_followup_callback(
            mock_callback_query, "suggestion_123", mock_context
        )

        # Verify message sent
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Follow-up" in call_args[0][0]


class TestHandleConversationCallback:
    """Tests for conversation control callbacks."""

    @pytest.mark.asyncio
    async def test_conversation_continue(self, mock_callback_query, mock_context):
        """Test conversation continue."""
        await handle_conversation_callback(
            mock_callback_query, "continue", mock_context
        )

        # Verify continue message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Continuing Conversation" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_conversation_end(self, mock_callback_query, mock_context):
        """Test conversation end."""
        mock_context.user_data["claude_session_id"] = "active_session"

        await handle_conversation_callback(mock_callback_query, "end", mock_context)

        # Verify session cleared
        assert mock_context.user_data.get("claude_session_id") is None

        # Verify message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Conversation Ended" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_conversation_unknown_action(self, mock_callback_query, mock_context):
        """Test unknown conversation action."""
        await handle_conversation_callback(
            mock_callback_query, "unknown", mock_context
        )

        # Verify unknown action message
        call_args = mock_callback_query.edit_message_text.call_args
        assert "Unknown Conversation Action" in call_args[0][0]


class TestCallbackIntegration:
    """Integration tests for callback handlers."""

    @pytest.mark.asyncio
    async def test_full_navigation_workflow(
        self, mock_callback_query, mock_context, temp_approved_dir
    ):
        """Test complete navigation workflow through callbacks."""
        # 1. Start at root
        mock_context.user_data["current_directory"] = temp_approved_dir

        # 2. Navigate to project
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path.return_value = (
            True,
            temp_approved_dir / "project1",
            None,
        )

        await handle_cd_callback(mock_callback_query, "project1", mock_context)

        assert mock_context.user_data["current_directory"] == temp_approved_dir / "project1"

        # 3. List files in project
        await handle_action_callback(mock_callback_query, "ls", mock_context)

        # 4. Navigate back to root
        await handle_cd_callback(mock_callback_query, "/", mock_context)

        assert mock_context.user_data["current_directory"] == temp_approved_dir

    @pytest.mark.asyncio
    async def test_session_lifecycle_workflow(self, mock_callback_query, mock_context):
        """Test complete session lifecycle through callbacks."""
        # 1. Start new session
        await handle_action_callback(mock_callback_query, "new_session", mock_context)

        assert mock_context.user_data.get("session_started") is True

        # 2. Check status
        await handle_action_callback(mock_callback_query, "status", mock_context)

        # 3. End session
        mock_context.user_data["claude_session_id"] = "test_session"

        from src.bot.handlers.callback import _handle_end_session_action

        await _handle_end_session_action(mock_callback_query, mock_context)

        assert mock_context.user_data.get("claude_session_id") is None
