"""Backpressure queue tests for Claude SDK streaming."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from claude_agent_sdk import ResultMessage
from claude_agent_sdk.types import StreamEvent

from src.claude.sdk_integration import ClaudeSDKManager, StreamUpdate
from src.config.settings import Settings


def _make_result_message(**kwargs):
    defaults = {
        "subtype": "success",
        "duration_ms": 1000,
        "duration_api_ms": 800,
        "is_error": False,
        "num_turns": 1,
        "session_id": "test-session",
        "total_cost_usd": 0.01,
        "result": "done",
    }
    defaults.update(kwargs)
    return ResultMessage(**defaults)


def _make_stream_delta(text: str, idx: int = 1) -> StreamEvent:
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


async def test_stream_worker_flushes_before_result_and_stops_on_sentinel(tmp_path):
    """ResultMessage stops producer/consumer after pending stream deltas are drained."""
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

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(
                _make_stream_delta("hello"),
                _make_result_message(),
            ),
        ),
    ):
        response = await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
            stream_callback=stream_callback,
        )

    assert response.session_id == "test-session"
    assert [update.type for update in updates] == ["stream_delta"]
    assert updates[0].content == "hello"
