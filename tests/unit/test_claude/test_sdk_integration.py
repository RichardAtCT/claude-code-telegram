"""Test Claude SDK integration."""

import asyncio
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from src.claude.sdk_integration import ClaudeResponse, ClaudeSDKManager, StreamUpdate
from src.config.settings import Settings
from src.exceptions import ConfigurationError


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


def _mock_client(*messages):
    """Create a mock ClaudeSDKClient that yields the given messages.

    Returns a factory function suitable for patching ClaudeSDKClient.
    """
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.query = AsyncMock()

    async def receive_response():
        for msg in messages:
            yield msg

    client.receive_response = receive_response

    return client


def _mock_client_factory(*messages, capture_options=None):
    """Create a factory that returns a mock client, optionally capturing options."""

    def factory(options):
        if capture_options is not None:
            capture_options.append(options)
        return _mock_client(*messages)

    return factory


class TestClaudeSDKManager:
    """Test Claude SDK manager."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config without API key."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
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
            claude_timeout_seconds=2,
        )

        # Store original env var
        original_api_key = os.environ.get("ANTHROPIC_API_KEY")

        try:
            ClaudeSDKManager(config_with_key)

            # Check that API key was set in environment
            assert os.environ.get("ANTHROPIC_API_KEY") == "test-api-key"

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

            ClaudeSDKManager(config)

            # Check that no API key was set (should use CLI auth)
            assert config.anthropic_api_key_str is None

        finally:
            # Restore original env var
            if original_api_key:
                os.environ["ANTHROPIC_API_KEY"] = original_api_key

    async def test_execute_command_success(self, sdk_manager):
        """Test successful command execution."""
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(session_id="test-session", total_cost_usd=0.05),
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            response = await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
                session_id="test-session",
            )

        # Verify response
        assert isinstance(response, ClaudeResponse)
        assert response.session_id == "test-session"
        assert response.duration_ms >= 0
        assert not response.is_error
        assert response.cost == 0.05

    async def test_execute_command_uses_result_content(self, sdk_manager):
        """Test that ResultMessage.result is used for content when available."""
        mock_factory = _mock_client_factory(
            _make_assistant_message("Assistant text"),
            _make_result_message(result="Final result from ResultMessage"),
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            response = await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
            )

        assert response.content == "Final result from ResultMessage"

    async def test_execute_command_falls_back_to_messages(self, sdk_manager):
        """Test fallback to message extraction when result is None."""
        mock_factory = _mock_client_factory(
            _make_assistant_message("Extracted from messages"),
            _make_result_message(result=None),
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            response = await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
            )

        assert response.content == "Extracted from messages"

    async def test_execute_command_with_streaming(self, sdk_manager):
        """Test command execution with streaming callback."""
        stream_updates = []

        async def stream_callback(update: StreamUpdate):
            stream_updates.append(update)

        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(),
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
                stream_callback=stream_callback,
            )

        # Verify streaming was called
        assert len(stream_updates) > 0
        assert any(update.type == "assistant" for update in stream_updates)

    async def test_execute_command_timeout(self, sdk_manager):
        """Test command execution timeout."""
        from src.claude.exceptions import ClaudeTimeoutError

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.query = AsyncMock()

        async def hanging_receive():
            await asyncio.sleep(5)  # Exceeds 2s timeout
            yield  # Never reached

        client.receive_response = hanging_receive

        with patch("src.claude.sdk_integration.ClaudeSDKClient", return_value=client):
            with pytest.raises(ClaudeTimeoutError):
                await sdk_manager.execute_command(
                    prompt="Test prompt",
                    working_directory=Path("/test"),
                )

    def test_get_active_process_count(self, sdk_manager):
        """Test active process count is always 0."""
        assert sdk_manager.get_active_process_count() == 0

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
            claude_timeout_seconds=2,
            enable_mcp=True,
            mcp_config_path=str(mcp_config_file),
        )

        manager = ClaudeSDKManager(config)

        captured_options = []
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(total_cost_usd=0.01),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
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
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(total_cost_usd=0.01),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=Path("/test"),
            )

        # Verify MCP config was NOT set (should be empty default)
        assert len(captured_options) == 1
        assert captured_options[0].mcp_servers == {}

    async def test_execute_command_passes_resume_session(self, sdk_manager):
        """Test that session_id is passed as options.resume for continuation."""
        captured_options = []
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(session_id="test-session"),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await sdk_manager.execute_command(
                prompt="Continue working",
                working_directory=Path("/test"),
                session_id="existing-session-id",
                continue_session=True,
            )

        assert len(captured_options) == 1
        assert captured_options[0].resume == "existing-session-id"

    async def test_execute_command_no_resume_for_new_session(self, sdk_manager):
        """Test that resume is not set for new sessions."""
        captured_options = []
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(session_id="new-session"),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await sdk_manager.execute_command(
                prompt="New prompt",
                working_directory=Path("/test"),
                session_id=None,
                continue_session=False,
            )

        assert len(captured_options) == 1
        assert (
            not hasattr(captured_options[0], "resume") or not captured_options[0].resume
        )


class TestClaudeSandboxSettings:
    """Test sandbox and system_prompt settings on ClaudeAgentOptions."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with sandbox enabled."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            sandbox_enabled=True,
            sandbox_excluded_commands=["git", "npm"],
        )

    @pytest.fixture
    def sdk_manager(self, config):
        return ClaudeSDKManager(config)

    async def test_sandbox_settings_passed_to_options(self, sdk_manager, tmp_path):
        """Test that sandbox settings are set on ClaudeAgentOptions."""
        captured_options = []
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(total_cost_usd=0.01),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=tmp_path,
            )

        assert len(captured_options) == 1
        opts = captured_options[0]
        assert opts.sandbox == {
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
            "excludedCommands": ["git", "npm"],
        }

    async def test_system_prompt_set_with_working_directory(
        self, sdk_manager, tmp_path
    ):
        """Test that system_prompt references the working directory."""
        captured_options = []
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(total_cost_usd=0.01),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await sdk_manager.execute_command(
                prompt="Test prompt",
                working_directory=tmp_path,
            )

        assert len(captured_options) == 1
        opts = captured_options[0]
        assert str(tmp_path) in opts.system_prompt
        assert "relative paths" in opts.system_prompt.lower()

    async def test_disallowed_tools_passed_to_options(self, tmp_path):
        """Test that disallowed_tools from config are passed to ClaudeAgentOptions."""
        config = Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            claude_disallowed_tools=["WebFetch", "WebSearch"],
        )
        manager = ClaudeSDKManager(config)

        captured_options = []
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(total_cost_usd=0.01),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await manager.execute_command(
                prompt="Test prompt",
                working_directory=tmp_path,
            )

        assert len(captured_options) == 1
        assert captured_options[0].disallowed_tools == ["WebFetch", "WebSearch"]

    async def test_sandbox_disabled_when_config_false(self, tmp_path):
        """Test sandbox is disabled when sandbox_enabled=False."""
        config = Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            sandbox_enabled=False,
        )
        manager = ClaudeSDKManager(config)

        captured_options = []
        mock_factory = _mock_client_factory(
            _make_assistant_message("Test response"),
            _make_result_message(total_cost_usd=0.01),
            capture_options=captured_options,
        )

        with patch(
            "src.claude.sdk_integration.ClaudeSDKClient", side_effect=mock_factory
        ):
            await manager.execute_command(
                prompt="Test prompt",
                working_directory=tmp_path,
            )

        assert len(captured_options) == 1
        assert captured_options[0].sandbox["enabled"] is False


class TestClaudeMCPErrors:
    """Test MCP-specific error handling."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
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

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.query = AsyncMock(
            side_effect=CLIConnectionError("MCP server failed to start")
        )

        with patch("src.claude.sdk_integration.ClaudeSDKClient", return_value=client):
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

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.query = AsyncMock(
            side_effect=ProcessError("Failed to start MCP server: connection refused")
        )

        with patch("src.claude.sdk_integration.ClaudeSDKClient", return_value=client):
            with pytest.raises(ClaudeMCPError) as exc_info:
                await sdk_manager.execute_command(
                    prompt="Test prompt",
                    working_directory=Path("/test"),
                )

        assert "MCP" in str(exc_info.value)


class TestCheckAuthentication:
    """Test authentication check at startup."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config without API key."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
        )

    @pytest.fixture
    def config_with_key(self, tmp_path):
        """Create test config with API key."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            anthropic_api_key="sk-ant-test-key",
            claude_timeout_seconds=2,
        )

    async def test_auth_passes_with_api_key(self, config_with_key):
        """Test that auth check passes when ANTHROPIC_API_KEY is set."""
        manager = ClaudeSDKManager(config_with_key)
        # Should not raise
        await manager.check_authentication()

    async def test_auth_passes_with_cli(self, config):
        """Test that auth check passes when Claude CLI is found and works."""
        manager = ClaudeSDKManager(config)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1.0.0"

        # Remove API key from env to force CLI path
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch(
                "src.claude.sdk_integration.find_claude_cli",
                return_value="/usr/local/bin/claude",
            ):
                with patch("subprocess.run", return_value=mock_result):
                    await manager.check_authentication()

    async def test_auth_fails_no_key_no_cli(self, config):
        """Test that auth check fails when neither API key nor CLI is available."""
        manager = ClaudeSDKManager(config)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("src.claude.sdk_integration.find_claude_cli", return_value=None):
                with pytest.raises(
                    ConfigurationError, match="No Claude authentication"
                ):
                    await manager.check_authentication()

    async def test_auth_fails_cli_returns_error(self, config):
        """Test that auth check fails when CLI returns non-zero exit code."""
        manager = ClaudeSDKManager(config)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch(
                "src.claude.sdk_integration.find_claude_cli",
                return_value="/usr/local/bin/claude",
            ):
                with patch("subprocess.run", return_value=mock_result):
                    with pytest.raises(ConfigurationError, match="returned an error"):
                        await manager.check_authentication()

    async def test_auth_fails_cli_timeout(self, config):
        """Test that auth check fails when CLI times out."""
        manager = ClaudeSDKManager(config)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch(
                "src.claude.sdk_integration.find_claude_cli",
                return_value="/usr/local/bin/claude",
            ):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=10),
                ):
                    with pytest.raises(ConfigurationError, match="timed out"):
                        await manager.check_authentication()

    async def test_auth_fails_cli_not_found_at_runtime(self, config):
        """Test that auth check fails when CLI path disappears."""
        manager = ClaudeSDKManager(config)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch(
                "src.claude.sdk_integration.find_claude_cli",
                return_value="/usr/local/bin/claude",
            ):
                with patch("subprocess.run", side_effect=FileNotFoundError()):
                    with pytest.raises(
                        ConfigurationError, match="no longer accessible"
                    ):
                        await manager.check_authentication()

    async def test_api_key_in_env_takes_priority_over_cli(self, config):
        """Test that API key in environment is checked before CLI."""
        manager = ClaudeSDKManager(config)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            # Should pass without ever checking CLI
            with patch("src.claude.sdk_integration.find_claude_cli") as mock_find:
                await manager.check_authentication()
                mock_find.assert_not_called()
