"""Test Claude SDK integration."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
)

from src.claude.sdk_integration import ClaudeResponse, ClaudeSDKManager, StreamUpdate
from src.config.settings import Settings


def _make_assistant_message(text="Test response"):
    """Create an AssistantMessage with proper structure for current SDK version."""
    return AssistantMessage(
        content=[TextBlock(text=text)],
        model="claude-sonnet-4-20250514",
    )


def _make_result_message(**kwargs):
    """Create a ResultMessage with sensible defaults."""
    defaults = {
        "subtype": "success",
        "duration_ms": 1000,
        "duration_api_ms": 800,
        "is_error": False,
        "num_turns": 1,
        "session_id": "test-session",
        "total_cost_usd": 0.05,
        "result": "Success",
    }
    defaults.update(kwargs)
    return ResultMessage(**defaults)


class TestClaudeSDKManager:
    """Test Claude SDK manager."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config without API key."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            use_sdk=True,
            claude_timeout_seconds=2,  # Short timeout for testing
        )

    @pytest.fixture
    def sdk_manager(self, config):
        """Create SDK manager."""
        return ClaudeSDKManager(config)

    async def test_sdk_manager_initialization_with_api_key(self, tmp_path):
        """Test SDK manager initialization with API key."""
        from src.config.settings import Settings

        # Test with API key provided
        config_with_key = Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            anthropic_api_key="test-api-key",
            use_sdk=True,
            claude_timeout_seconds=2,
        )

        # Store original env var
        original_api_key = os.environ.get("ANTHROPIC_API_KEY")

        try:
            manager = ClaudeSDKManager(config_with_key)

            # Check that API key was set in environment
            assert os.environ.get("ANTHROPIC_API_KEY") == "test-api-key"
            assert manager.active_sessions == {}

        finally:
            # Restore original env var
            if original_api_key:
                os.environ["ANTHROPIC_API_KEY"] = original_api_key
            elif "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

    async def test_sdk_manager_initialization_without_api_key(self, config):
        """Test SDK manager initialization without API key (uses CLI auth)."""
        # Store original env var
        original_api_key = os.environ.get("ANTHROPIC_API_KEY")

        try:
            # Remove any existing API key
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

            manager = ClaudeSDKManager(config)

            # Check that no API key was set (should use CLI auth)
            assert config.anthropic_api_key_str is None
            assert manager.active_sessions == {}

        finally:
            # Restore original env var
            if original_api_key:
                os.environ["ANTHROPIC_API_KEY"] = original_api_key

    async def test_execute_command_success(self, sdk_manager):
        """Test successful command execution."""

        async def mock_query(prompt, options):
            yield _make_assistant_message("Test response")
            yield _make_result_message(session_id="test-session", total_cost_usd=0.05)

        with patch("src.claude.sdk_integration.query", side_effect=mock_query):
            response = await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
                session_id="test-session",
            )

        # Verify response
        assert isinstance(response, ClaudeResponse)
        assert response.session_id == "test-session"
        assert response.duration_ms >= 0  # Can be 0 in tests
        assert not response.is_error
        assert response.cost == 0.05

    async def test_execute_command_with_streaming(self, sdk_manager):
        """Test command execution with streaming callback."""
        stream_updates = []

        async def stream_callback(update: StreamUpdate):
            stream_updates.append(update)

        async def mock_query(prompt, options):
            yield _make_assistant_message("Test response")
            yield _make_result_message()

        with patch("src.claude.sdk_integration.query", side_effect=mock_query):
            response = await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
                stream_callback=stream_callback,
            )

        # Verify streaming was called
        assert len(stream_updates) > 0
        assert any(update.type == "assistant" for update in stream_updates)

    async def test_execute_command_timeout(self, sdk_manager):
        """Test command execution timeout."""
        import asyncio

        # Mock a hanging operation - return async generator that never yields
        async def mock_hanging_query(prompt, options):
            await asyncio.sleep(5)  # This should timeout (config has 2s timeout)
            yield  # This will never be reached

        from src.claude.exceptions import ClaudeTimeoutError

        with patch("src.claude.sdk_integration.query", side_effect=mock_hanging_query):
            with pytest.raises(ClaudeTimeoutError):
                await sdk_manager.execute_command(
                    prompt="Test prompt",
                    working_directory=Path("/test"),
                )

    async def test_session_management(self, sdk_manager):
        """Test session management."""
        session_id = "test-session"
        messages = [_make_assistant_message("test")]

        # Update session
        sdk_manager._update_session(session_id, messages)

        # Verify session was created
        assert session_id in sdk_manager.active_sessions
        session_data = sdk_manager.active_sessions[session_id]
        assert session_data["messages"] == messages

    async def test_kill_all_processes(self, sdk_manager):
        """Test killing all processes (clearing sessions)."""
        # Add some active sessions
        sdk_manager.active_sessions["session1"] = {"test": "data"}
        sdk_manager.active_sessions["session2"] = {"test": "data2"}

        assert len(sdk_manager.active_sessions) == 2

        # Kill all processes
        await sdk_manager.kill_all_processes()

        # Sessions should be cleared
        assert len(sdk_manager.active_sessions) == 0

    def test_get_active_process_count(self, sdk_manager):
        """Test getting active process count."""
        assert sdk_manager.get_active_process_count() == 0

        # Add sessions
        sdk_manager.active_sessions["session1"] = {"test": "data"}
        sdk_manager.active_sessions["session2"] = {"test": "data2"}

        assert sdk_manager.get_active_process_count() == 2

    async def test_execute_command_passes_mcp_config(self, tmp_path):
        """Test that MCP config is passed to ClaudeAgentOptions when enabled."""
        # Create a valid MCP config file
        mcp_config_file = tmp_path / "mcp_config.json"
        mcp_config_file.write_text(
            '{"mcpServers": {"test-server": {"command": "echo", "args": ["hello"]}}}'
        )

        config = Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            use_sdk=True,
            claude_timeout_seconds=2,
            enable_mcp=True,
            mcp_config_path=str(mcp_config_file),
        )

        manager = ClaudeSDKManager(config)

        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield _make_assistant_message("Test response")
            yield _make_result_message(total_cost_usd=0.01)

        with patch("src.claude.sdk_integration.query", side_effect=mock_query):
            await manager.execute_command(
                prompt="Test prompt",
                working_directory=tmp_path,
            )

        # Verify MCP config was parsed and passed as dict to options
        assert len(captured_options) == 1
        assert captured_options[0].mcp_servers == {
            "test-server": {"command": "echo", "args": ["hello"]}
        }

    async def test_execute_command_no_mcp_when_disabled(self, sdk_manager):
        """Test that MCP config is NOT passed when MCP is disabled."""
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield _make_assistant_message("Test response")
            yield _make_result_message(total_cost_usd=0.01)

        with patch("src.claude.sdk_integration.query", side_effect=mock_query):
            await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
            )

        # Verify MCP config was NOT set (should be empty default)
        assert len(captured_options) == 1
        assert captured_options[0].mcp_servers == {}


class TestClaudeMCPErrors:
    """Test MCP-specific error handling."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            use_sdk=True,
            claude_timeout_seconds=2,
        )

    @pytest.fixture
    def sdk_manager(self, config):
        """Create SDK manager."""
        return ClaudeSDKManager(config)

    async def test_mcp_connection_error_raises_mcp_error(self, sdk_manager):
        """Test that MCP connection errors raise ClaudeMCPError."""
        from claude_agent_sdk import CLIConnectionError

        from src.claude.exceptions import ClaudeMCPError

        async def mock_query(prompt, options):
            raise CLIConnectionError("MCP server failed to start")
            yield  # make it an async generator

        with patch("src.claude.sdk_integration.query", side_effect=mock_query):
            with pytest.raises(ClaudeMCPError) as exc_info:
                await sdk_manager.execute_command(
                    prompt="Test prompt",
                    working_directory=Path("/test"),
                )

        assert "MCP server" in str(exc_info.value)

    async def test_mcp_process_error_raises_mcp_error(self, sdk_manager):
        """Test that MCP process errors raise ClaudeMCPError."""
        from claude_agent_sdk import ProcessError

        from src.claude.exceptions import ClaudeMCPError

        async def mock_query(prompt, options):
            raise ProcessError("Failed to start MCP server: connection refused")
            yield  # make it an async generator

        with patch("src.claude.sdk_integration.query", side_effect=mock_query):
            with pytest.raises(ClaudeMCPError) as exc_info:
                await sdk_manager.execute_command(
                    prompt="Test prompt",
                    working_directory=Path("/test"),
                )

        assert "MCP" in str(exc_info.value)
