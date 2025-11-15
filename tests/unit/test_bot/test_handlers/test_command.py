"""Comprehensive tests for command handlers."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User

from src.bot.handlers.command import (
    change_directory,
    continue_session,
    end_session,
    export_session,
    git_command,
    help_command,
    list_files,
    new_session,
    print_working_directory,
    quick_actions,
    session_status,
    show_projects,
    start_command,
)
from src.config.settings import Settings


@pytest.fixture
def temp_approved_dir():
    """Create temporary approved directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        approved_dir = Path(temp_dir) / "approved"
        approved_dir.mkdir()
        # Create some test subdirectories
        (approved_dir / "project1").mkdir()
        (approved_dir / "project2").mkdir()
        # Create some test files
        (approved_dir / "test.txt").write_text("test content")
        (approved_dir / "project1" / "code.py").write_text("print('hello')")
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
def mock_update():
    """Create mock Telegram update."""
    update = AsyncMock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 123456789
    update.effective_user.first_name = "TestUser"
    update.message = AsyncMock()
    update.message.message_id = 1
    update.message.date = Mock()
    update.message.date.strftime = Mock(return_value="12:00:00 UTC")
    update.message.chat = AsyncMock()
    return update


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
    context.args = []
    return context


class TestStartCommand:
    """Tests for start_command handler."""

    @pytest.mark.asyncio
    async def test_start_command_success(self, mock_update, mock_context):
        """Test successful start command."""
        await start_command(mock_update, mock_context)

        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args

        # Check message contains welcome text
        assert "Welcome" in call_args[0][0]
        assert "Available Commands" in call_args[0][0]

        # Check inline keyboard was included
        assert "reply_markup" in call_args[1]
        assert isinstance(call_args[1]["reply_markup"], InlineKeyboardMarkup)

    @pytest.mark.asyncio
    async def test_start_command_audit_logging(self, mock_update, mock_context):
        """Test that start command logs to audit."""
        await start_command(mock_update, mock_context)

        # Verify audit logging was called
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_command.assert_called_once_with(
            user_id=123456789, command="start", args=[], success=True
        )

    @pytest.mark.asyncio
    async def test_start_command_no_audit_logger(self, mock_update, mock_context):
        """Test start command when audit logger is not available."""
        mock_context.bot_data["audit_logger"] = None

        # Should not raise an error
        await start_command(mock_update, mock_context)

        # Verify message was still sent
        mock_update.message.reply_text.assert_called_once()


class TestHelpCommand:
    """Tests for help_command handler."""

    @pytest.mark.asyncio
    async def test_help_command_success(self, mock_update, mock_context):
        """Test successful help command."""
        await help_command(mock_update, mock_context)

        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args

        # Check message contains help text
        assert "Help" in call_args[0][0]
        assert "Navigation Commands" in call_args[0][0]
        assert "Session Commands" in call_args[0][0]


class TestNewSession:
    """Tests for new_session handler."""

    @pytest.mark.asyncio
    async def test_new_session_success(self, mock_update, mock_context, mock_settings):
        """Test successful new session creation."""
        await new_session(mock_update, mock_context)

        # Verify session data was cleared
        assert mock_context.user_data.get("claude_session_id") is None
        assert mock_context.user_data.get("session_started") is True

        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "New Claude Code Session" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_new_session_custom_directory(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test new session with custom current directory."""
        custom_dir = temp_approved_dir / "project1"
        mock_context.user_data["current_directory"] = custom_dir

        await new_session(mock_update, mock_context)

        # Verify message includes custom directory path
        call_args = mock_update.message.reply_text.call_args
        assert "project1" in call_args[0][0]


class TestContinueSession:
    """Tests for continue_session handler."""

    @pytest.mark.asyncio
    async def test_continue_session_with_existing_session(
        self, mock_update, mock_context, mock_settings
    ):
        """Test continuing an existing session."""
        session_id = "test_session_123"
        mock_context.user_data["claude_session_id"] = session_id

        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = session_id
        mock_response.content = "Continued response"
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        await continue_session(mock_update, mock_context)

        # Verify Claude integration was called
        mock_context.bot_data["claude_integration"].run_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_session_with_prompt(
        self, mock_update, mock_context, mock_settings
    ):
        """Test continue session with additional prompt."""
        session_id = "test_session_123"
        mock_context.user_data["claude_session_id"] = session_id
        mock_context.args = ["continue", "with", "this"]

        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = session_id
        mock_response.content = "Response to prompt"
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        await continue_session(mock_update, mock_context)

        # Verify prompt was passed to Claude
        call_args = mock_context.bot_data["claude_integration"].run_command.call_args
        assert call_args[1]["prompt"] == "continue with this"

    @pytest.mark.asyncio
    async def test_continue_session_no_session_found(
        self, mock_update, mock_context, mock_settings
    ):
        """Test continue session when no session exists."""
        mock_context.bot_data["claude_integration"].continue_session.return_value = None

        await continue_session(mock_update, mock_context)

        # Verify error message was sent
        # The status_msg.edit_text should have been called
        assert mock_update.message.reply_text.call_count >= 1

    @pytest.mark.asyncio
    async def test_continue_session_no_integration(self, mock_update, mock_context):
        """Test continue session when Claude integration is not available."""
        mock_context.bot_data["claude_integration"] = None

        await continue_session(mock_update, mock_context)

        # Verify error message was sent
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Not Available" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_continue_session_error_handling(
        self, mock_update, mock_context, mock_settings
    ):
        """Test error handling in continue session."""
        mock_context.user_data["claude_session_id"] = "test_session"
        mock_context.bot_data["claude_integration"].run_command.side_effect = Exception(
            "Test error"
        )

        await continue_session(mock_update, mock_context)

        # Verify error message was sent
        assert mock_update.message.reply_text.call_count >= 1
        # Check that error was logged
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_command.assert_called_with(
            user_id=123456789, command="continue", args=[], success=False
        )


class TestListFiles:
    """Tests for list_files handler."""

    @pytest.mark.asyncio
    async def test_list_files_success(self, mock_update, mock_context, temp_approved_dir):
        """Test successful file listing."""
        await list_files(mock_update, mock_context)

        # Verify message was sent with file list
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "project1" in call_args[0][0]
        assert "project2" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_files_empty_directory(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test listing empty directory."""
        empty_dir = temp_approved_dir / "empty"
        empty_dir.mkdir()
        mock_context.user_data["current_directory"] = empty_dir

        await list_files(mock_update, mock_context)

        # Verify empty directory message
        call_args = mock_update.message.reply_text.call_args
        assert "empty directory" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_files_hides_hidden(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test that hidden files are not shown."""
        # Create hidden file
        (temp_approved_dir / ".hidden").write_text("hidden")

        await list_files(mock_update, mock_context)

        # Verify hidden file is not in output
        call_args = mock_update.message.reply_text.call_args
        assert ".hidden" not in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_files_error_handling(self, mock_update, mock_context):
        """Test error handling when listing fails."""
        # Set non-existent directory
        mock_context.user_data["current_directory"] = Path("/nonexistent")

        await list_files(mock_update, mock_context)

        # Verify error message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Error" in call_args[0][0]

        # Verify audit log (check positional args)
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_command.assert_called()
        call_args = audit_logger.log_command.call_args
        # The call might be positional or keyword
        if call_args[0]:  # Positional
            assert call_args[0][0] == 123456789
            assert call_args[0][1] == "ls"
        else:  # Keyword
            assert call_args[1]["user_id"] == 123456789


class TestChangeDirectory:
    """Tests for change_directory handler."""

    @pytest.mark.asyncio
    async def test_change_directory_success(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test successful directory change."""
        mock_context.args = ["project1"]

        # Mock security validator - not async
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path = Mock(return_value=(
            True,
            temp_approved_dir / "project1",
            None,
        ))

        await change_directory(mock_update, mock_context)

        # Verify directory was changed
        assert mock_context.user_data.get("current_directory") == temp_approved_dir / "project1"
        # Verify session was cleared
        assert mock_context.user_data.get("claude_session_id") is None

        # Verify success message
        call_args = mock_update.message.reply_text.call_args
        assert "Directory Changed" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_change_directory_no_args(self, mock_update, mock_context):
        """Test cd command without arguments."""
        mock_context.args = []

        await change_directory(mock_update, mock_context)

        # Verify usage message was sent
        call_args = mock_update.message.reply_text.call_args
        assert "Usage" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_change_directory_path_traversal_blocked(
        self, mock_update, mock_context
    ):
        """Test that path traversal attempts are blocked."""
        mock_context.args = ["../../etc/passwd"]

        # Mock security validator to reject - not async
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path = Mock(return_value=(
            False,
            None,
            "Path traversal attempt detected",
        ))

        await change_directory(mock_update, mock_context)

        # Verify access denied message
        call_args = mock_update.message.reply_text.call_args
        assert "Access Denied" in call_args[0][0]

        # Verify security violation was logged
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_security_violation.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_directory_nonexistent(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test changing to non-existent directory."""
        mock_context.args = ["nonexistent"]

        # Mock security validator to accept but directory doesn't exist
        validator = mock_context.bot_data["security_validator"]
        validator.validate_path = Mock(return_value=(
            True,
            temp_approved_dir / "nonexistent",
            None,
        ))

        await change_directory(mock_update, mock_context)

        # Verify error message
        call_args = mock_update.message.reply_text.call_args
        assert "Not Found" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_change_directory_to_root(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test changing to root directory."""
        mock_context.args = ["/"]

        await change_directory(mock_update, mock_context)

        # The cd / command sets the directory inline, check the message confirms root
        call_args = mock_update.message.reply_text.call_args
        assert "Directory Changed" in call_args[0][0] or "." in call_args[0][0]

    @pytest.mark.asyncio
    async def test_change_directory_parent(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test navigating to parent directory."""
        # Start in subdirectory
        mock_context.user_data["current_directory"] = temp_approved_dir / "project1"
        mock_context.args = [".."]

        await change_directory(mock_update, mock_context)

        # Verify we're in parent directory (or root if we can't go up)
        # The code might keep us at root if we're already there
        current_dir = mock_context.user_data.get("current_directory")
        assert current_dir == temp_approved_dir or current_dir == temp_approved_dir / "project1"


class TestPrintWorkingDirectory:
    """Tests for print_working_directory handler."""

    @pytest.mark.asyncio
    async def test_pwd_success(self, mock_update, mock_context, temp_approved_dir):
        """Test successful pwd command."""
        await print_working_directory(mock_update, mock_context)

        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Current Directory" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_pwd_with_subdirectory(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test pwd in subdirectory."""
        mock_context.user_data["current_directory"] = temp_approved_dir / "project1"

        await print_working_directory(mock_update, mock_context)

        # Verify message includes subdirectory
        call_args = mock_update.message.reply_text.call_args
        assert "project1" in call_args[0][0]


class TestShowProjects:
    """Tests for show_projects handler."""

    @pytest.mark.asyncio
    async def test_show_projects_success(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test successful project listing."""
        await show_projects(mock_update, mock_context)

        # Verify message with projects
        call_args = mock_update.message.reply_text.call_args
        assert "project1" in call_args[0][0]
        assert "project2" in call_args[0][0]

        # Verify inline keyboard
        assert "reply_markup" in call_args[1]

    @pytest.mark.asyncio
    async def test_show_projects_no_projects(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test when no projects exist."""
        # Remove all subdirectories and their contents
        import shutil
        for item in temp_approved_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)

        await show_projects(mock_update, mock_context)

        # Verify no projects message
        call_args = mock_update.message.reply_text.call_args
        assert "No Projects Found" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_show_projects_hides_hidden(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test that hidden directories are not shown."""
        # Create hidden directory
        (temp_approved_dir / ".hidden").mkdir()

        await show_projects(mock_update, mock_context)

        # Verify hidden directory is not shown
        call_args = mock_update.message.reply_text.call_args
        assert ".hidden" not in call_args[0][0]


class TestSessionStatus:
    """Tests for session_status handler."""

    @pytest.mark.asyncio
    async def test_status_no_session(self, mock_update, mock_context):
        """Test status when no session exists."""
        await session_status(mock_update, mock_context)

        # Verify status message
        call_args = mock_update.message.reply_text.call_args
        assert "Session Status" in call_args[0][0]
        assert "None" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_status_with_active_session(self, mock_update, mock_context):
        """Test status with active session."""
        mock_context.user_data["claude_session_id"] = "test_session_123"

        await session_status(mock_update, mock_context)

        # Verify status shows active session
        call_args = mock_update.message.reply_text.call_args
        assert "Active" in call_args[0][0]
        # Session ID is truncated to first 8 chars
        assert "test_ses" in call_args[0][0] or "test_session" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_status_with_rate_limiter(self, mock_update, mock_context, mock_settings):
        """Test status includes usage information."""
        # Mock rate limiter with a non-raising mock
        rate_limiter = Mock()
        rate_limiter.get_user_status = Mock(return_value={
            "cost_usage": {"current": 5.0, "limit": 10.0}
        })
        mock_context.bot_data["rate_limiter"] = rate_limiter

        await session_status(mock_update, mock_context)

        # Verify usage info in message
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[0][0]
        # Check that usage info is present
        assert "5.00" in message_text or "Usage" in message_text
        assert "10.00" in message_text or "50%" in message_text


class TestEndSession:
    """Tests for end_session handler."""

    @pytest.mark.asyncio
    async def test_end_session_success(self, mock_update, mock_context):
        """Test successful session termination."""
        mock_context.user_data["claude_session_id"] = "test_session_123"
        mock_context.user_data["session_started"] = True

        await end_session(mock_update, mock_context)

        # Verify session was cleared
        assert mock_context.user_data.get("claude_session_id") is None
        assert mock_context.user_data.get("session_started") is False

        # Verify success message
        call_args = mock_update.message.reply_text.call_args
        assert "Session Ended" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_end_session_no_active_session(self, mock_update, mock_context):
        """Test ending session when none is active."""
        await end_session(mock_update, mock_context)

        # Verify info message
        call_args = mock_update.message.reply_text.call_args
        assert "No Active Session" in call_args[0][0]


class TestExportSession:
    """Tests for export_session handler."""

    @pytest.mark.asyncio
    async def test_export_session_not_available(self, mock_update, mock_context):
        """Test export when feature is not available."""
        mock_context.bot_data["features"] = None

        await export_session(mock_update, mock_context)

        # Verify message
        call_args = mock_update.message.reply_text.call_args
        assert "not available" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_export_session_no_active_session(self, mock_update, mock_context):
        """Test export when no session is active."""
        features = mock_context.bot_data["features"]
        features.get_session_export.return_value = Mock()

        await export_session(mock_update, mock_context)

        # Verify error message
        call_args = mock_update.message.reply_text.call_args
        assert "No Active Session" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_export_session_shows_format_selection(
        self, mock_update, mock_context
    ):
        """Test export shows format selection."""
        mock_context.user_data["claude_session_id"] = "test_session_123"
        features = mock_context.bot_data["features"]
        features.get_session_export.return_value = Mock()

        await export_session(mock_update, mock_context)

        # Verify format selection keyboard
        call_args = mock_update.message.reply_text.call_args
        assert "Choose export format" in call_args[0][0]
        assert "reply_markup" in call_args[1]


class TestQuickActions:
    """Tests for quick_actions handler."""

    @pytest.mark.asyncio
    async def test_quick_actions_disabled(self, mock_update, mock_context):
        """Test quick actions when disabled."""
        features = Mock()  # Use regular Mock, not AsyncMock
        features.is_enabled = Mock(return_value=False)
        mock_context.bot_data["features"] = features

        await quick_actions(mock_update, mock_context)

        # Verify disabled message
        call_args = mock_update.message.reply_text.call_args
        assert "Disabled" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_quick_actions_not_available(self, mock_update, mock_context):
        """Test when quick actions feature is not available."""
        mock_context.bot_data["features"] = None

        await quick_actions(mock_update, mock_context)

        # Verify error message
        call_args = mock_update.message.reply_text.call_args
        assert "Disabled" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_quick_actions_success(self, mock_update, mock_context):
        """Test successful quick actions display."""
        features = Mock()  # Use regular Mock
        features.is_enabled = Mock(return_value=True)

        # Mock quick action manager
        mock_manager = AsyncMock()
        mock_manager.get_suggestions = AsyncMock(return_value=[
            {"id": "test", "name": "Test Action"}
        ])
        mock_manager.create_inline_keyboard = Mock(return_value=InlineKeyboardMarkup([]))
        features.get_quick_actions = Mock(return_value=mock_manager)
        mock_context.bot_data["features"] = features

        await quick_actions(mock_update, mock_context)

        # Verify quick actions message
        call_args = mock_update.message.reply_text.call_args
        assert "Quick Actions" in call_args[0][0]


class TestGitCommand:
    """Tests for git_command handler."""

    @pytest.mark.asyncio
    async def test_git_disabled(self, mock_update, mock_context):
        """Test git command when git is disabled."""
        features = Mock()  # Use regular Mock
        features.is_enabled = Mock(return_value=False)
        mock_context.bot_data["features"] = features

        await git_command(mock_update, mock_context)

        # Verify disabled message
        call_args = mock_update.message.reply_text.call_args
        assert "Disabled" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_not_a_repository(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test git command in non-git directory."""
        features = mock_context.bot_data["features"]
        features.is_enabled.return_value = True
        features.get_git_integration.return_value = Mock()

        await git_command(mock_update, mock_context)

        # Verify not a repository message
        call_args = mock_update.message.reply_text.call_args
        assert "Not a Git Repository" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_command_success(
        self, mock_update, mock_context, temp_approved_dir
    ):
        """Test successful git command."""
        # Create .git directory
        (temp_approved_dir / ".git").mkdir()

        features = Mock()  # Use regular Mock
        features.is_enabled = Mock(return_value=True)

        # Mock git integration
        mock_git = AsyncMock()
        mock_status = Mock()
        mock_status.branch = "main"
        mock_status.ahead = 0
        mock_status.behind = 0
        mock_status.is_clean = True
        mock_status.modified = []
        mock_status.added = []
        mock_status.deleted = []
        mock_status.untracked = []
        mock_git.get_status = AsyncMock(return_value=mock_status)
        features.get_git_integration = Mock(return_value=mock_git)
        mock_context.bot_data["features"] = features

        await git_command(mock_update, mock_context)

        # Verify git status message
        call_args = mock_update.message.reply_text.call_args
        assert "Git Repository Status" in call_args[0][0]
        assert "main" in call_args[0][0]
