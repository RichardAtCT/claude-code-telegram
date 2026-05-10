"""JAR-136 delivery observability tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import StreamEvent

from src.claude.exceptions import ClaudeProcessError
from src.claude.sdk_integration import (
    TASK_COMPLETED_MSG,
    ClaudeSDKManager,
    delivery_metrics_report,
    format_delivery_metrics_dashboard,
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


async def _execute_with_messages(tmp_path, *messages):
    manager = _make_manager(tmp_path)

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(*messages),
        ),
        patch("src.claude.sdk_integration.logger") as logger_mock,
    ):
        response = await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
        )

    return response, logger_mock


def _delivery_logs(logger_mock):
    return [
        call
        for call in logger_mock.info.call_args_list
        if call.args and call.args[0] == "delivery"
    ]


async def test_result_message_text_logs_final_user_response_without_raw_body(tmp_path):
    response, logger_mock = await _execute_with_messages(
        tmp_path,
        _make_result_message(result="Final answer body"),
    )

    assert response.content == "Final answer body"
    delivery_log = _delivery_logs(logger_mock)[-1]
    assert delivery_log.kwargs["delivery_kind"] == "final_user_response"
    assert delivery_log.kwargs["content_source"] == "result_message"
    assert delivery_log.kwargs["content_length"] == len("Final answer body")
    assert "Final answer body" not in repr(delivery_log)


async def test_reconstructed_textblock_logs_final_user_response(tmp_path):
    response, logger_mock = await _execute_with_messages(
        tmp_path,
        AssistantMessage(
            content=[TextBlock(text="TextBlock final answer")],
            model="claude-sonnet-4-20250514",
        ),
        _make_result_message(result=None),
    )

    assert response.content == "TextBlock final answer"
    delivery_log = _delivery_logs(logger_mock)[-1]
    assert delivery_log.kwargs["delivery_kind"] == "final_user_response"
    assert delivery_log.kwargs["content_source"] == "assistant_text"


async def test_stream_reconstruction_logs_final_user_response(tmp_path):
    response, logger_mock = await _execute_with_messages(
        tmp_path,
        _make_stream_delta("stream ", 0),
        _make_stream_delta("answer", 1),
        _make_result_message(result=""),
    )

    assert response.content == "stream answer"
    delivery_log = _delivery_logs(logger_mock)[-1]
    assert delivery_log.kwargs["delivery_kind"] == "final_user_response"
    assert delivery_log.kwargs["content_source"] == "stream_delta"


async def test_task_completed_fallback_logs_tool_summary_internal(tmp_path):
    response, logger_mock = await _execute_with_messages(
        tmp_path,
        AssistantMessage(
            content=[ToolUseBlock(id="tool-1", name="Bash", input={"command": "ls"})],
            model="claude-sonnet-4-20250514",
        ),
        _make_result_message(result=None),
    )

    assert response.content == TASK_COMPLETED_MSG.format(tools_summary="Bash")
    delivery_log = _delivery_logs(logger_mock)[-1]
    assert delivery_log.kwargs["delivery_kind"] == "tool_summary_internal"
    assert delivery_log.kwargs["content_source"] == "tool_summary_fallback"
    assert delivery_log.kwargs["tools_count"] == 1


async def test_error_path_logs_error_fallback_metadata_only(tmp_path):
    manager = _make_manager(tmp_path)
    client = AsyncMock()
    client.connect = AsyncMock(side_effect=RuntimeError("boom raw details"))
    client.disconnect = AsyncMock()

    with (
        patch("src.claude.sdk_integration.ClaudeSDKClient", return_value=client),
        patch("src.claude.sdk_integration.logger") as logger_mock,
        pytest.raises(ClaudeProcessError),
    ):
        await manager.execute_command(prompt="Test", working_directory=Path("/test"))

    delivery_log = _delivery_logs(logger_mock)[-1]
    assert delivery_log.kwargs["delivery_kind"] == "error_fallback"
    assert delivery_log.kwargs["error_type"] == "RuntimeError"
    assert "boom raw details" not in repr(delivery_log)


def test_delivery_metrics_report_counts_daily_tool_summary_rate():
    report = delivery_metrics_report(
        [
            {
                "event": "delivery",
                "delivery_kind": "final_user_response",
                "timestamp": "2026-05-10T10:00:00Z",
            },
            {
                "event": "claude_run_complete",
                "timestamp": "2026-05-10T10:30:00Z",
            },
            {
                "event": "delivery",
                "delivery_kind": "tool_summary_internal",
                "timestamp": "2026-05-10T11:00:00Z",
            },
            {
                "event": "delivery",
                "delivery_kind": "tool_summary_internal",
                "timestamp": "2026-05-10T12:00:00Z",
            },
        ]
    )

    assert report == [
        {
            "date": "2026-05-10",
            "total": 3,
            "tool_summary_internal": 2,
            "tool_summary_internal_rate": pytest.approx(2 / 3),
            "alert": True,
        }
    ]


def test_format_delivery_metrics_dashboard_highlights_alerts():
    dashboard = format_delivery_metrics_dashboard(
        [
            {
                "date": "2026-05-10",
                "total": 20,
                "tool_summary_internal": 2,
                "tool_summary_internal_rate": 0.10,
                "alert": True,
            }
        ]
    )

    assert "2026-05-10" in dashboard
    assert "10.00%" in dashboard
    assert "ALERT" in dashboard
