"""Regression tests ensuring Claude thinking content is never streamed to Telegram."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ThinkingBlock
from claude_agent_sdk.types import StreamEvent

from src.claude.sdk_integration import ClaudeSDKManager, StreamUpdate
from src.config.settings import Settings


SECRET_THINKING = "INTERNAL_THINKING_MUST_NOT_REACH_TELEGRAM"


def _make_result_message() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=800,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        total_cost_usd=0.01,
        result="final result",
    )


def _make_thinking_delta(text: str, idx: int) -> StreamEvent:
    return StreamEvent(
        uuid=f"think-{idx}",
        session_id="test-session",
        event={
            "type": "content_block_delta",
            "delta": {"type": "thinking_delta", "thinking": text},
        },
    )


def _make_text_delta(text: str, idx: int) -> StreamEvent:
    return StreamEvent(
        uuid=f"text-{idx}",
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


async def test_thinking_delta_is_not_sent_to_stream_callback(tmp_path):
    manager = ClaudeSDKManager(
        Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            enable_mcp=False,
        )
    )
    updates: list[StreamUpdate] = []

    async def stream_callback(update: StreamUpdate) -> None:
        updates.append(update)

    messages = [
        _make_thinking_delta(SECRET_THINKING, 1),
        _make_text_delta("visible text", 2),
        _make_result_message(),
    ]

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(*messages),
        ),
    ):
        await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
            stream_callback=stream_callback,
        )

    rendered = "\n".join(update.content or "" for update in updates)
    assert "visible text" in rendered
    assert SECRET_THINKING not in rendered


async def test_assistant_thinking_block_is_not_sent_to_stream_callback(tmp_path):
    manager = ClaudeSDKManager(
        Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            enable_mcp=False,
        )
    )
    updates: list[StreamUpdate] = []

    async def stream_callback(update: StreamUpdate) -> None:
        updates.append(update)

    assistant_message = AssistantMessage(
        content=[
            ThinkingBlock(thinking=SECRET_THINKING, signature="sig"),
            TextBlock(text="visible final text"),
        ],
        model="claude-sonnet-4-20250514",
    )

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(assistant_message, _make_result_message()),
        ),
    ):
        await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
            stream_callback=stream_callback,
        )

    rendered = "\n".join(update.content or "" for update in updates)
    assert "visible final text" in rendered
    assert SECRET_THINKING not in rendered
