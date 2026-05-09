"""Regression tests for JAR-114: silence post-tool delivers TASK_COMPLETED_MSG.

The bug: when Claude uses tools (Bash/Grep/Read) and produces a substantive
final answer, the user receives the fallback ``TASK_COMPLETED_MSG`` template
("Task completed. Tools used: ...") instead of the real text.

These tests reproduce the scenarios where the fallback fires incorrectly.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import StreamEvent

from src.claude.sdk_integration import (
    TASK_COMPLETED_MSG,
    ClaudeSDKManager,
    StreamUpdate,
)
from src.config.settings import Settings


def _make_result_message(result=None) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=800,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        total_cost_usd=0.01,
        result=result,
    )


def _make_stream_delta(text: str, idx: int) -> StreamEvent:
    return StreamEvent(
        uuid=f"evt-{idx}",
        session_id="test-session",
        event={
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": text},
        },
    )


def _mock_client(*messages):
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.query = AsyncMock()

    async def receive_raw_messages():
        for msg in messages:
            yield msg

    query_mock = AsyncMock()
    query_mock.receive_messages = receive_raw_messages
    client._query = query_mock
    return client


def _make_manager(tmp_path):
    return ClaudeSDKManager(
        Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            enable_mcp=False,
        )
    )


async def test_empty_string_result_with_tools_does_not_use_fallback_when_stream_has_text(
    tmp_path,
):
    """ResultMessage.result == "" + tools used + stream-only text should NOT yield
    the TASK_COMPLETED_MSG fallback."""
    manager = _make_manager(tmp_path)

    tool_message = AssistantMessage(
        content=[ToolUseBlock(id="tool-1", name="Bash", input={"command": "ls"})],
        model="claude-sonnet-4-20250514",
    )
    # Real-world reproducer: tool runs, then text streams as deltas (no final
    # AssistantMessage with TextBlock), and ResultMessage carries an empty
    # string result instead of the assembled text.
    messages = [
        tool_message,
        _make_stream_delta("Hello, ", 0),
        _make_stream_delta("the directory is empty.", 1),
        _make_result_message(result=""),
    ]

    async def stream_callback(update: StreamUpdate) -> None:
        pass

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(*messages),
        ),
    ):
        response = await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
            stream_callback=stream_callback,
        )

    assert response.content != TASK_COMPLETED_MSG.format(tools_summary="Bash"), (
        "Empty-string ResultMessage.result + tool calls must not trigger "
        "the TASK_COMPLETED_MSG fallback when the streamed text is available."
    )
    assert "Task completed" not in response.content
    assert "Hello" in response.content or "directory is empty" in response.content


async def test_tools_then_final_textblock_uses_real_text_when_result_is_none(
    tmp_path,
):
    """ResultMessage.result is None, but a final AssistantMessage(TextBlock)
    arrived after the tool use — real text must win, not the fallback."""
    manager = _make_manager(tmp_path)

    tool_message = AssistantMessage(
        content=[ToolUseBlock(id="tool-1", name="Read", input={"file_path": "x.py"})],
        model="claude-sonnet-4-20250514",
    )
    final_text = AssistantMessage(
        content=[TextBlock(text="Here is the substantive answer.")],
        model="claude-sonnet-4-20250514",
    )
    messages = [
        tool_message,
        final_text,
        _make_result_message(result=None),
    ]

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(*messages),
        ),
    ):
        response = await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
        )

    assert response.content == "Here is the substantive answer."
    assert "Task completed" not in response.content


async def test_tools_with_only_stream_deltas_and_none_result_uses_streamed_text(
    tmp_path,
):
    """Stream-only text + tool calls + ResultMessage.result is None: the
    streamed text must be reconstructed, not replaced by TASK_COMPLETED_MSG."""
    manager = _make_manager(tmp_path)

    tool_message = AssistantMessage(
        content=[ToolUseBlock(id="tool-1", name="Grep", input={"pattern": "foo"})],
        model="claude-sonnet-4-20250514",
    )
    messages = [
        tool_message,
        _make_stream_delta("Found 3 matches in ", 0),
        _make_stream_delta("the codebase.", 1),
        _make_result_message(result=None),
    ]

    async def stream_callback(update: StreamUpdate) -> None:
        pass

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(*messages),
        ),
    ):
        response = await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
            stream_callback=stream_callback,
        )

    assert "Task completed" not in response.content, (
        f"Got fallback message instead of real text: {response.content!r}"
    )
    assert "Found 3 matches" in response.content
