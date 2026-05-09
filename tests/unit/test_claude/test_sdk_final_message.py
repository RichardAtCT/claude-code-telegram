"""Final assistant message delivery tests for Claude SDK backpressure."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import StreamEvent

from src.claude.sdk_integration import ClaudeSDKManager, StreamUpdate
from src.config.settings import Settings


def _make_result_message() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=800,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        total_cost_usd=0.01,
        result="done",
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


async def test_final_textblock_is_delivered_after_many_dropped_deltas(
    tmp_path, monkeypatch
):
    """Assistant TextBlock final messages are never dropped or coalesced."""
    monkeypatch.setattr("src.claude.sdk_integration.SDK_STREAM_QUEUE_MAXSIZE", 1)
    manager = ClaudeSDKManager(
        Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            enable_mcp=False,
        )
    )
    release_first_callback = asyncio.Event()
    first_callback_started = asyncio.Event()
    updates: list[StreamUpdate] = []

    async def stream_callback(update: StreamUpdate) -> None:
        updates.append(update)
        if update.tool_calls:
            first_callback_started.set()
            await release_first_callback.wait()

    tool_message = AssistantMessage(
        content=[ToolUseBlock(id="tool-1", name="Read", input={"file_path": "a.py"})],
        model="claude-sonnet-4-20250514",
    )
    final_text = AssistantMessage(
        content=[TextBlock(text="final answer")],
        model="claude-sonnet-4-20250514",
    )
    messages = [
        tool_message,
        *[_make_stream_delta("x", i) for i in range(100)],
        final_text,
        _make_result_message(),
    ]

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(*messages),
        ),
        patch("src.claude.sdk_integration.logger") as logger_mock,
    ):
        task = asyncio.create_task(
            manager.execute_command(
                prompt="Test",
                working_directory=Path("/test"),
                stream_callback=stream_callback,
            )
        )
        await asyncio.wait_for(first_callback_started.wait(), timeout=1)
        await asyncio.sleep(0)
        release_first_callback.set()
        response = await task

    assert response.content == "done"
    assert any(
        update.type == "assistant" and update.content == "final answer"
        for update in updates
    )
    complete_logs = [
        call
        for call in logger_mock.info.call_args_list
        if call.args and call.args[0] == "claude_run_complete"
    ]
    assert complete_logs[-1].kwargs["dropped_count"] > 0
