"""Test Claude integration facade."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.claude.facade import ClaudeIntegration
from src.claude.integration import ClaudeProcessManager, ClaudeResponse, StreamUpdate
from src.claude.monitor import ToolMonitor
from src.claude.session import ClaudeSession, SessionManager
from src.config.loader import create_test_config


class TestClaudeIntegration:
    """Test ClaudeIntegration facade."""

    @pytest.fixture
    def config(self, tmp_path):
        """Test configuration."""
        return create_test_config(
            approved_directory=str(tmp_path),
            use_sdk=False,  # Use subprocess by default for testing
            claude_allowed_tools=["Read", "Write", "Edit", "Bash"],
        )

    @pytest.fixture
    def mock_session_manager(self):
        """Mock session manager."""
        manager = Mock(spec=SessionManager)
        manager.get_or_create_session = AsyncMock()
        manager.update_session = AsyncMock()
        manager.get_session_info = AsyncMock()
        manager._get_user_sessions = AsyncMock(return_value=[])
        manager.cleanup_expired_sessions = AsyncMock(return_value=0)
        manager.get_user_session_summary = AsyncMock(
            return_value={"total_sessions": 0, "total_cost": 0.0}
        )
        return manager

    @pytest.fixture
    def mock_tool_monitor(self):
        """Mock tool monitor."""
        monitor = Mock(spec=ToolMonitor)
        monitor.validate_tool_call = AsyncMock(return_value=(True, None))
        monitor.get_tool_stats = Mock(
            return_value={
                "total_calls": 0,
                "by_tool": {},
                "unique_tools": 0,
                "security_violations": 0,
            }
        )
        monitor.get_user_tool_usage = Mock(
            return_value={
                "user_id": 123,
                "security_violations": 0,
                "violation_types": [],
            }
        )
        return monitor

    @pytest.fixture
    def mock_process_manager(self):
        """Mock process manager."""
        manager = Mock(spec=ClaudeProcessManager)
        manager.execute_command = AsyncMock()
        manager.kill_all_processes = AsyncMock()
        return manager

    @pytest.fixture
    def integration(
        self, config, mock_process_manager, mock_session_manager, mock_tool_monitor
    ):
        """Test integration instance."""
        return ClaudeIntegration(
            config=config,
            process_manager=mock_process_manager,
            session_manager=mock_session_manager,
            tool_monitor=mock_tool_monitor,
        )

    def test_integration_initialization_with_subprocess(self, config, tmp_path):
        """Test integration initialization with subprocess."""
        integration = ClaudeIntegration(config)

        assert integration.config == config
        assert integration.process_manager is not None
        assert integration.manager == integration.process_manager
        assert integration.sdk_manager is None

    def test_integration_initialization_with_sdk(self, tmp_path):
        """Test integration initialization with SDK."""
        config = create_test_config(
            approved_directory=str(tmp_path),
            use_sdk=True,
        )
        integration = ClaudeIntegration(config)

        assert integration.sdk_manager is not None
        assert integration.manager == integration.sdk_manager

    def test_integration_initialization_with_custom_managers(
        self, config, mock_process_manager, mock_session_manager, mock_tool_monitor
    ):
        """Test integration initialization with custom managers."""
        integration = ClaudeIntegration(
            config=config,
            process_manager=mock_process_manager,
            session_manager=mock_session_manager,
            tool_monitor=mock_tool_monitor,
        )

        assert integration.process_manager == mock_process_manager
        assert integration.session_manager == mock_session_manager
        assert integration.tool_monitor == mock_tool_monitor

    @pytest.mark.asyncio
    async def test_run_command_success(
        self, integration, mock_session_manager, mock_process_manager, tmp_path
    ):
        """Test successful command execution."""
        # Setup mock session
        mock_session = Mock(spec=ClaudeSession)
        mock_session.session_id = "session123"
        mock_session.is_new_session = False
        mock_session_manager.get_or_create_session.return_value = mock_session

        # Setup mock response
        mock_response = ClaudeResponse(
            content="Task completed",
            session_id="session123",
            cost=0.05,
            duration_ms=1000,
            num_turns=3,
        )
        mock_process_manager.execute_command.return_value = mock_response

        # Execute command
        response = await integration.run_command(
            prompt="Test prompt",
            working_directory=tmp_path,
            user_id=123,
        )

        assert response.content == "Task completed"
        assert response.session_id == "session123"
        assert mock_session_manager.get_or_create_session.called
        assert mock_session_manager.update_session.called
        assert mock_process_manager.execute_command.called

    @pytest.mark.asyncio
    async def test_run_command_with_session_id(
        self, integration, mock_session_manager, mock_process_manager, tmp_path
    ):
        """Test command execution with existing session."""
        mock_session = Mock(spec=ClaudeSession)
        mock_session.session_id = "existing_session"
        mock_session.is_new_session = False
        mock_session_manager.get_or_create_session.return_value = mock_session

        mock_response = ClaudeResponse(
            content="Done",
            session_id="existing_session",
            cost=0.03,
            duration_ms=500,
            num_turns=1,
        )
        mock_process_manager.execute_command.return_value = mock_response

        response = await integration.run_command(
            prompt="Continue",
            working_directory=tmp_path,
            user_id=123,
            session_id="existing_session",
        )

        assert response.session_id == "existing_session"

    @pytest.mark.asyncio
    async def test_run_command_new_session(
        self, integration, mock_session_manager, mock_process_manager, tmp_path
    ):
        """Test command execution creating new session."""
        mock_session = Mock(spec=ClaudeSession)
        mock_session.session_id = "temp_new_session"
        mock_session.is_new_session = True
        mock_session_manager.get_or_create_session.return_value = mock_session

        mock_response = ClaudeResponse(
            content="New session started",
            session_id="claude_session_id",
            cost=0.02,
            duration_ms=300,
            num_turns=1,
        )
        mock_process_manager.execute_command.return_value = mock_response

        response = await integration.run_command(
            prompt="Start new",
            working_directory=tmp_path,
            user_id=123,
        )

        # Should use Claude's session ID for new sessions
        assert response.session_id == "claude_session_id"

    @pytest.mark.asyncio
    async def test_run_command_with_stream_callback(
        self, integration, mock_session_manager, mock_process_manager, tmp_path
    ):
        """Test command execution with streaming."""
        mock_session = Mock(spec=ClaudeSession)
        mock_session.session_id = "session123"
        mock_session.is_new_session = False
        mock_session_manager.get_or_create_session.return_value = mock_session

        mock_response = ClaudeResponse(
            content="Done",
            session_id="session123",
            cost=0.01,
            duration_ms=200,
            num_turns=1,
        )
        mock_process_manager.execute_command.return_value = mock_response

        stream_updates = []

        async def on_stream(update):
            stream_updates.append(update)

        await integration.run_command(
            prompt="Test",
            working_directory=tmp_path,
            user_id=123,
            on_stream=on_stream,
        )

        # Stream handler should be passed to process manager
        call_kwargs = mock_process_manager.execute_command.call_args.kwargs
        assert "stream_callback" in call_kwargs

    @pytest.mark.asyncio
    async def test_continue_session_success(
        self, integration, mock_session_manager, mock_process_manager, tmp_path
    ):
        """Test continuing an existing session."""
        # Setup existing session
        existing_session = Mock(spec=ClaudeSession)
        existing_session.session_id = "existing123"
        existing_session.project_path = tmp_path
        existing_session.last_used = Mock()
        existing_session.is_new_session = False

        mock_session_manager._get_user_sessions.return_value = [existing_session]
        mock_session_manager.get_or_create_session.return_value = existing_session

        mock_response = ClaudeResponse(
            content="Continued",
            session_id="existing123",
            cost=0.02,
            duration_ms=400,
            num_turns=2,
        )
        mock_process_manager.execute_command.return_value = mock_response

        response = await integration.continue_session(
            user_id=123,
            working_directory=tmp_path,
            prompt="Continue please",
        )

        assert response is not None
        assert response.session_id == "existing123"

    @pytest.mark.asyncio
    async def test_continue_session_no_sessions(
        self, integration, mock_session_manager, tmp_path
    ):
        """Test continuing session when none exist."""
        mock_session_manager._get_user_sessions.return_value = []

        response = await integration.continue_session(
            user_id=123,
            working_directory=tmp_path,
        )

        assert response is None

    @pytest.mark.asyncio
    async def test_continue_session_different_directory(
        self, integration, mock_session_manager, tmp_path
    ):
        """Test continuing session in different directory."""
        other_path = tmp_path / "other"
        other_path.mkdir()

        existing_session = Mock(spec=ClaudeSession)
        existing_session.session_id = "session123"
        existing_session.project_path = other_path
        existing_session.last_used = Mock()

        mock_session_manager._get_user_sessions.return_value = [existing_session]

        response = await integration.continue_session(
            user_id=123,
            working_directory=tmp_path,  # Different path
        )

        assert response is None

    @pytest.mark.asyncio
    async def test_get_session_info(self, integration, mock_session_manager):
        """Test getting session information."""
        mock_session_manager.get_session_info.return_value = {
            "session_id": "session123",
            "total_cost": 0.15,
        }

        info = await integration.get_session_info("session123")

        assert info["session_id"] == "session123"
        assert mock_session_manager.get_session_info.called

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, integration, mock_session_manager, tmp_path):
        """Test getting user sessions."""
        from datetime import datetime

        mock_session = Mock(spec=ClaudeSession)
        mock_session.session_id = "session123"
        mock_session.project_path = tmp_path
        mock_session.created_at = datetime.utcnow()
        mock_session.last_used = datetime.utcnow()
        mock_session.total_cost = 0.10
        mock_session.message_count = 5
        mock_session.tools_used = ["Read", "Write"]
        mock_session.is_expired.return_value = False

        mock_session_manager._get_user_sessions.return_value = [mock_session]

        sessions = await integration.get_user_sessions(123)

        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "session123"
        assert sessions[0]["total_cost"] == 0.10
        assert sessions[0]["expired"] is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, integration, mock_session_manager):
        """Test cleaning up expired sessions."""
        mock_session_manager.cleanup_expired_sessions.return_value = 3

        count = await integration.cleanup_expired_sessions()

        assert count == 3
        assert mock_session_manager.cleanup_expired_sessions.called

    @pytest.mark.asyncio
    async def test_get_tool_stats(self, integration, mock_tool_monitor):
        """Test getting tool statistics."""
        stats = await integration.get_tool_stats()

        assert "total_calls" in stats
        assert mock_tool_monitor.get_tool_stats.called

    @pytest.mark.asyncio
    async def test_get_user_summary(
        self, integration, mock_session_manager, mock_tool_monitor
    ):
        """Test getting user summary."""
        summary = await integration.get_user_summary(123)

        assert "user_id" in summary
        assert summary["user_id"] == 123
        assert mock_session_manager.get_user_session_summary.called
        assert mock_tool_monitor.get_user_tool_usage.called

    @pytest.mark.asyncio
    async def test_shutdown(self, integration, mock_process_manager, mock_session_manager):
        """Test shutdown procedure."""
        await integration.shutdown()

        assert mock_process_manager.kill_all_processes.called
        assert mock_session_manager.cleanup_expired_sessions.called

    def test_get_admin_instructions(self, integration):
        """Test generating admin instructions."""
        blocked_tools = ["WebSearch", "TodoWrite"]
        instructions = integration._get_admin_instructions(blocked_tools)

        assert "CLAUDE_ALLOWED_TOOLS" in instructions
        assert "WebSearch" in instructions
        assert "TodoWrite" in instructions

    def test_create_tool_error_message(self, integration):
        """Test creating tool error message."""
        blocked_tools = ["WebSearch"]
        allowed_tools = ["Read", "Write"]
        admin_instructions = "Instructions here"

        message = integration._create_tool_error_message(
            blocked_tools, allowed_tools, admin_instructions
        )

        assert "Tool Access Blocked" in message
        assert "WebSearch" in message
        assert "Read" in message or "Write" in message
        assert admin_instructions in message

    @pytest.mark.asyncio
    async def test_execute_with_fallback_subprocess_only(
        self, integration, mock_process_manager, tmp_path
    ):
        """Test execute with fallback using subprocess only."""
        mock_response = ClaudeResponse(
            content="Done",
            session_id="session123",
            cost=0.01,
            duration_ms=100,
            num_turns=1,
        )
        mock_process_manager.execute_command.return_value = mock_response

        response = await integration._execute_with_fallback(
            prompt="Test",
            working_directory=tmp_path,
        )

        assert response.content == "Done"
        assert mock_process_manager.execute_command.called

    @pytest.mark.asyncio
    async def test_execute_with_fallback_sdk_success(self, tmp_path):
        """Test execute with fallback using SDK successfully."""
        config = create_test_config(
            approved_directory=str(tmp_path),
            use_sdk=True,
        )

        mock_sdk_manager = Mock()
        mock_sdk_manager.execute_command = AsyncMock(
            return_value=ClaudeResponse(
                content="SDK success",
                session_id="sdk123",
                cost=0.02,
                duration_ms=200,
                num_turns=1,
            )
        )

        integration = ClaudeIntegration(
            config=config,
            sdk_manager=mock_sdk_manager,
        )

        response = await integration._execute_with_fallback(
            prompt="Test",
            working_directory=tmp_path,
        )

        assert response.content == "SDK success"
        assert integration._sdk_failed_count == 0

    @pytest.mark.asyncio
    async def test_sdk_failed_count_tracking(self, integration):
        """Test SDK failure count tracking."""
        assert integration._sdk_failed_count == 0

        # Simulate SDK failures would increment the counter
        # This is tested in the actual fallback logic

    @pytest.mark.asyncio
    async def test_run_command_error_handling(
        self, integration, mock_session_manager, mock_process_manager, tmp_path
    ):
        """Test error handling in run_command."""
        mock_session = Mock(spec=ClaudeSession)
        mock_session.session_id = "session123"
        mock_session.is_new_session = False
        mock_session_manager.get_or_create_session.return_value = mock_session

        # Simulate process manager error
        mock_process_manager.execute_command.side_effect = Exception("Process failed")

        with pytest.raises(Exception, match="Process failed"):
            await integration.run_command(
                prompt="Test",
                working_directory=tmp_path,
                user_id=123,
            )
