"""Test Claude subprocess integration."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.claude.integration import (
    ClaudeProcessManager,
    ClaudeResponse,
    StreamUpdate,
)
from src.config.loader import create_test_config


class TestClaudeResponse:
    """Test ClaudeResponse dataclass."""

    def test_claude_response_creation(self):
        """Test creating ClaudeResponse."""
        response = ClaudeResponse(
            content="Test response",
            session_id="session123",
            cost=0.05,
            duration_ms=1000,
            num_turns=3,
        )

        assert response.content == "Test response"
        assert response.session_id == "session123"
        assert response.cost == 0.05
        assert response.duration_ms == 1000
        assert response.num_turns == 3
        assert response.is_error is False
        assert response.error_type is None
        assert response.tools_used == []

    def test_claude_response_with_error(self):
        """Test creating ClaudeResponse with error."""
        response = ClaudeResponse(
            content="Error occurred",
            session_id="session123",
            cost=0.0,
            duration_ms=100,
            num_turns=1,
            is_error=True,
            error_type="timeout",
        )

        assert response.is_error is True
        assert response.error_type == "timeout"

    def test_claude_response_with_tools(self):
        """Test creating ClaudeResponse with tools used."""
        tools = [
            {"name": "Read", "timestamp": "2024-01-01"},
            {"name": "Write", "timestamp": "2024-01-01"},
        ]
        response = ClaudeResponse(
            content="Done",
            session_id="session123",
            cost=0.1,
            duration_ms=2000,
            num_turns=5,
            tools_used=tools,
        )

        assert len(response.tools_used) == 2
        assert response.tools_used[0]["name"] == "Read"


class TestStreamUpdate:
    """Test StreamUpdate dataclass."""

    def test_stream_update_creation(self):
        """Test creating StreamUpdate."""
        update = StreamUpdate(
            type="assistant",
            content="Test content",
        )

        assert update.type == "assistant"
        assert update.content == "Test content"
        assert update.tool_calls is None

    def test_stream_update_is_error(self):
        """Test is_error method."""
        error_update = StreamUpdate(type="error", content="Error message")
        assert error_update.is_error() is True

        normal_update = StreamUpdate(type="assistant", content="Normal message")
        # is_error() returns True/False, not None
        result = normal_update.is_error()
        assert result is False or result is None  # Handle both cases

        metadata_error = StreamUpdate(
            type="assistant",
            content="Test",
            metadata={"is_error": True}
        )
        assert metadata_error.is_error() is True

    def test_stream_update_get_tool_names(self):
        """Test get_tool_names method."""
        tool_calls = [
            {"name": "Read", "input": {}},
            {"name": "Write", "input": {}},
        ]
        update = StreamUpdate(type="assistant", tool_calls=tool_calls)

        tool_names = update.get_tool_names()
        assert tool_names == ["Read", "Write"]

    def test_stream_update_get_tool_names_empty(self):
        """Test get_tool_names with no tool calls."""
        update = StreamUpdate(type="assistant", content="Test")
        assert update.get_tool_names() == []

    def test_stream_update_get_progress_percentage(self):
        """Test get_progress_percentage method."""
        update = StreamUpdate(
            type="progress",
            progress={"percentage": 75, "step": 3, "total_steps": 4}
        )
        assert update.get_progress_percentage() == 75

    def test_stream_update_get_progress_percentage_none(self):
        """Test get_progress_percentage with no progress."""
        update = StreamUpdate(type="assistant", content="Test")
        assert update.get_progress_percentage() is None

    def test_stream_update_get_error_message(self):
        """Test get_error_message method."""
        error_update = StreamUpdate(
            type="error",
            error_info={"message": "Something went wrong"}
        )
        assert error_update.get_error_message() == "Something went wrong"

        content_error = StreamUpdate(type="error", content="Error content")
        assert content_error.get_error_message() == "Error content"

    def test_stream_update_get_error_message_none(self):
        """Test get_error_message with no error."""
        update = StreamUpdate(type="assistant", content="Test")
        assert update.get_error_message() is None


class TestClaudeProcessManager:
    """Test ClaudeProcessManager class."""

    @pytest.fixture
    def config(self, tmp_path):
        """Test configuration."""
        return create_test_config(
            approved_directory=str(tmp_path),
            claude_timeout_seconds=30,
            claude_max_turns=10,
            claude_allowed_tools=["Read", "Write", "Bash"],
        )

    @pytest.fixture
    def manager(self, config):
        """Test process manager."""
        return ClaudeProcessManager(config)

    def test_manager_initialization(self, manager, config):
        """Test manager initialization."""
        assert manager.config == config
        assert manager.active_processes == {}
        assert manager.max_message_buffer == 1000
        assert manager.streaming_buffer_size == 65536

    def test_build_command_new_session(self, manager):
        """Test building command for new session."""
        cmd = manager._build_command("Hello", None, False)

        assert "claude" in cmd[0] or cmd[0].endswith("claude")
        assert "-p" in cmd
        assert "Hello" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--max-turns" in cmd

    def test_build_command_continue_session(self, manager):
        """Test building command to continue session."""
        cmd = manager._build_command("", "session123", True)

        assert "--continue" in cmd
        assert "--resume" in cmd
        assert "session123" in cmd

    def test_build_command_resume_with_prompt(self, manager):
        """Test building command to resume with new prompt."""
        cmd = manager._build_command("New message", "session123", True)

        assert "--resume" in cmd
        assert "session123" in cmd
        assert "-p" in cmd
        assert "New message" in cmd

    def test_build_command_with_allowed_tools(self, manager):
        """Test building command with allowed tools."""
        cmd = manager._build_command("Test", None, False)

        assert "--allowedTools" in cmd
        # Find the tools list after --allowedTools
        tools_idx = cmd.index("--allowedTools") + 1
        assert "Read,Write,Bash" in cmd[tools_idx]

    def test_validate_message_structure_valid(self, manager):
        """Test validating valid message structure."""
        msg = {"type": "assistant", "content": "test"}
        assert manager._validate_message_structure(msg) is True

    def test_validate_message_structure_invalid(self, manager):
        """Test validating invalid message structure."""
        msg = {"content": "test"}  # Missing 'type'
        assert manager._validate_message_structure(msg) is False

    def test_parse_assistant_message(self, manager):
        """Test parsing assistant message."""
        msg = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "World"},
                ]
            },
            "timestamp": "2024-01-01",
        }

        update = manager._parse_assistant_message(msg)

        assert update.type == "assistant"
        assert update.content == "Hello\nWorld"
        assert update.timestamp == "2024-01-01"

    def test_parse_assistant_message_with_tool_calls(self, manager):
        """Test parsing assistant message with tool calls."""
        msg = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "I'll read the file"},
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"path": "test.py"},
                        "id": "tool123",
                    },
                ]
            },
        }

        update = manager._parse_assistant_message(msg)

        assert update.content == "I'll read the file"
        assert len(update.tool_calls) == 1
        assert update.tool_calls[0]["name"] == "Read"
        assert update.tool_calls[0]["input"]["path"] == "test.py"

    def test_parse_tool_result_message(self, manager):
        """Test parsing tool result message."""
        msg = {
            "type": "tool_result",
            "result": {"content": "File contents", "is_error": False},
            "tool_use_id": "tool123",
        }

        update = manager._parse_tool_result_message(msg)

        assert update.type == "tool_result"
        assert update.content == "File contents"
        assert update.metadata["tool_use_id"] == "tool123"
        assert update.metadata["is_error"] is False

    def test_parse_tool_result_message_error(self, manager):
        """Test parsing tool result with error."""
        msg = {
            "type": "tool_result",
            "result": {"content": "Error occurred", "is_error": True},
        }

        update = manager._parse_tool_result_message(msg)

        assert update.type == "tool_result"
        assert update.metadata["is_error"] is True
        assert update.error_info is not None

    def test_parse_user_message(self, manager):
        """Test parsing user message."""
        msg = {
            "type": "user",
            "message": {"content": "Hello Claude"},
        }

        update = manager._parse_user_message(msg)

        assert update.type == "user"
        assert update.content == "Hello Claude"

    def test_parse_user_message_block_format(self, manager):
        """Test parsing user message in block format."""
        msg = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "Claude"},
                ]
            },
        }

        update = manager._parse_user_message(msg)

        assert update.type == "user"
        assert update.content == "Hello\nClaude"

    def test_parse_system_message_init(self, manager):
        """Test parsing system init message."""
        msg = {
            "type": "system",
            "subtype": "init",
            "tools": ["Read", "Write"],
            "model": "claude-3-5-sonnet",
        }

        update = manager._parse_system_message(msg)

        assert update.type == "system"
        assert update.metadata["subtype"] == "init"
        assert update.metadata["tools"] == ["Read", "Write"]
        assert update.metadata["model"] == "claude-3-5-sonnet"

    def test_parse_system_message_generic(self, manager):
        """Test parsing generic system message."""
        msg = {
            "type": "system",
            "subtype": "status",
            "message": "Processing...",
        }

        update = manager._parse_system_message(msg)

        assert update.type == "system"
        assert update.content == "Processing..."
        assert update.metadata["subtype"] == "status"

    def test_parse_error_message(self, manager):
        """Test parsing error message."""
        msg = {
            "type": "error",
            "message": "Something went wrong",
            "code": "ERR_001",
        }

        update = manager._parse_error_message(msg)

        assert update.type == "error"
        assert update.content == "Something went wrong"
        assert update.error_info["code"] == "ERR_001"

    def test_parse_progress_message(self, manager):
        """Test parsing progress message."""
        msg = {
            "type": "progress",
            "message": "Processing step 2 of 4",
            "percentage": 50,
            "step": 2,
            "total_steps": 4,
        }

        update = manager._parse_progress_message(msg)

        assert update.type == "progress"
        assert update.content == "Processing step 2 of 4"
        assert update.progress["percentage"] == 50
        assert update.progress["step"] == 2

    def test_parse_stream_message_unknown_type(self, manager):
        """Test parsing unknown message type."""
        msg = {"type": "unknown", "data": "test"}

        update = manager._parse_stream_message(msg)

        assert update is None

    def test_parse_result(self, manager):
        """Test parsing final result."""
        result = {
            "type": "result",
            "result": "Task completed",
            "session_id": "session123",
            "cost_usd": 0.05,
            "duration_ms": 1500,
            "num_turns": 3,
        }

        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {},
                        }
                    ]
                },
                "timestamp": "2024-01-01",
            }
        ]

        response = manager._parse_result(result, messages)

        assert response.content == "Task completed"
        assert response.session_id == "session123"
        assert response.cost == 0.05
        assert response.duration_ms == 1500
        assert response.num_turns == 3
        assert len(response.tools_used) == 1
        assert response.tools_used[0]["name"] == "Read"

    @pytest.mark.asyncio
    async def test_read_stream_bounded(self, manager):
        """Test reading stream with bounds."""
        # Create mock stream
        mock_stream = AsyncMock()
        data = b"line1\nline2\nline3\n"
        mock_stream.read.side_effect = [data, b""]

        lines = []
        async for line in manager._read_stream_bounded(mock_stream):
            lines.append(line)

        assert lines == ["line1", "line2", "line3"]

    @pytest.mark.asyncio
    async def test_read_stream_bounded_partial_lines(self, manager):
        """Test reading stream with partial lines."""
        mock_stream = AsyncMock()
        mock_stream.read.side_effect = [
            b"partial",
            b" line\ncomplete line\n",
            b"",
        ]

        lines = []
        async for line in manager._read_stream_bounded(mock_stream):
            lines.append(line)

        assert "partial line" in lines
        assert "complete line" in lines

    def test_get_active_process_count(self, manager):
        """Test getting active process count."""
        assert manager.get_active_process_count() == 0

        # Add mock processes
        manager.active_processes["id1"] = Mock()
        manager.active_processes["id2"] = Mock()

        assert manager.get_active_process_count() == 2

    @pytest.mark.asyncio
    async def test_kill_all_processes(self, manager):
        """Test killing all processes."""
        # Create mock processes
        mock_process1 = Mock()
        mock_process1.kill = Mock()
        mock_process1.wait = AsyncMock()

        mock_process2 = Mock()
        mock_process2.kill = Mock()
        mock_process2.wait = AsyncMock()

        manager.active_processes["id1"] = mock_process1
        manager.active_processes["id2"] = mock_process2

        await manager.kill_all_processes()

        assert mock_process1.kill.called
        assert mock_process2.kill.called
        assert len(manager.active_processes) == 0

    @pytest.mark.asyncio
    async def test_kill_all_processes_with_error(self, manager):
        """Test killing processes when one fails."""
        mock_process1 = Mock()
        mock_process1.kill = Mock(side_effect=Exception("Kill failed"))
        mock_process1.wait = AsyncMock()

        mock_process2 = Mock()
        mock_process2.kill = Mock()
        mock_process2.wait = AsyncMock()

        manager.active_processes["id1"] = mock_process1
        manager.active_processes["id2"] = mock_process2

        # Should not raise even if one fails
        await manager.kill_all_processes()

        assert len(manager.active_processes) == 0
