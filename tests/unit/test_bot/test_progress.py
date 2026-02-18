"""Tests for ProgressUpdater."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.progress import ProgressUpdater
from src.claude.integration import StreamUpdate


@pytest.fixture
def progress_msg():
    """Mock Telegram message that supports edit_text and delete."""
    msg = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.delete = AsyncMock()
    return msg


@pytest.fixture
def updater(progress_msg):
    return ProgressUpdater(progress_msg)


async def test_no_updates_message_unchanged(updater, progress_msg):
    """If no stream events arrive, the message is never edited."""
    await updater.flush()
    progress_msg.edit_text.assert_not_called()


async def test_single_tool_call_auto_flushed(updater, progress_msg):
    """A single tool call auto-flushes immediately on first handle_update."""
    update = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/src/main.py"}}],
    )
    await updater.handle_update(update)

    # First handle_update triggers auto-flush immediately
    progress_msg.edit_text.assert_called_once()
    text = progress_msg.edit_text.call_args.args[0]
    assert "Reading" in text
    assert "main.py" in text


async def test_multiple_tools_queued_all_shown(progress_msg):
    """Multiple tool calls all appear in the flushed message."""
    updater = ProgressUpdater(progress_msg, min_interval=0.0)
    updates = [
        StreamUpdate(
            type="assistant",
            tool_calls=[{"name": "Read", "input": {"file_path": "/a.py"}}],
        ),
        StreamUpdate(
            type="assistant",
            tool_calls=[{"name": "Bash", "input": {"command": "pytest"}}],
        ),
        StreamUpdate(
            type="assistant",
            tool_calls=[{"name": "Edit", "input": {"file_path": "/b.py"}}],
        ),
    ]
    for u in updates:
        await updater.handle_update(u)

    text = progress_msg.edit_text.call_args.args[0]
    assert "Reading" in text
    assert "Running" in text
    assert "Editing" in text


async def test_rate_limiting_skips_rapid_flushes(updater, progress_msg):
    """Subsequent updates within min_interval are rate-limited."""
    update = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/a.py"}}],
    )
    await updater.handle_update(update)
    # First handle_update auto-flushes immediately
    assert progress_msg.edit_text.call_count == 1

    # Immediate second update — should be rate limited
    update2 = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Write", "input": {"file_path": "/b.py"}}],
    )
    await updater.handle_update(update2)
    assert progress_msg.edit_text.call_count == 1  # Still 1 — rate limited


async def test_flush_after_interval_succeeds(progress_msg):
    """Every handle_update flushes when min_interval=0."""
    updater = ProgressUpdater(progress_msg, min_interval=0.0)

    update1 = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/a.py"}}],
    )
    await updater.handle_update(update1)
    assert progress_msg.edit_text.call_count == 1

    update2 = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Write", "input": {"file_path": "/b.py"}}],
    )
    await updater.handle_update(update2)
    assert progress_msg.edit_text.call_count == 2


async def test_truncation_when_too_many_steps(updater, progress_msg):
    """Old steps are truncated when the message would exceed Telegram limits."""
    for i in range(200):
        update = StreamUpdate(
            type="assistant",
            tool_calls=[
                {
                    "name": "Read",
                    "input": {"file_path": f"/very/long/path/to/some/deeply/nested/file_{i}.py"},
                }
            ],
        )
        await updater.handle_update(update)

    updater._min_interval = 0.0
    await updater.flush()

    text = progress_msg.edit_text.call_args.args[0]
    assert len(text) < 4096
    assert "earlier" in text.lower()


async def test_edit_failure_silently_ignored(updater, progress_msg):
    """If editMessageText fails, no exception propagates."""
    progress_msg.edit_text = AsyncMock(side_effect=Exception("Telegram error"))

    update = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/a.py"}}],
    )
    await updater.handle_update(update)
    await updater.flush()  # Should not raise


async def test_tool_name_mapping(updater, progress_msg):
    """All known tool names map to human-friendly labels."""
    tool_map = {
        "Read": "Reading",
        "Write": "Writing",
        "Edit": "Editing",
        "MultiEdit": "Editing",
        "Bash": "Running",
        "Grep": "Searching",
        "Glob": "Finding files",
        "WebFetch": "Fetching",
        "WebSearch": "Searching web",
        "Task": "Running subtask",
        "LS": "Listing",
    }
    for tool_name, expected_label in tool_map.items():
        u = ProgressUpdater(AsyncMock())
        u._min_interval = 0.0
        update = StreamUpdate(
            type="assistant",
            tool_calls=[{"name": tool_name, "input": {}}],
        )
        await u.handle_update(update)
        await u.flush()
        text = u._message.edit_text.call_args.args[0]
        assert (
            expected_label.lower() in text.lower()
        ), f"Tool {tool_name} should map to label containing '{expected_label}'"


async def test_assistant_text_not_shown_as_step(updater, progress_msg):
    """Pure text content from assistant (no tools) does not create a step."""
    update = StreamUpdate(type="assistant", content="Let me help you with that.")
    await updater.handle_update(update)
    await updater.flush()
    progress_msg.edit_text.assert_not_called()


async def test_handle_update_triggers_auto_flush(progress_msg):
    """handle_update auto-flushes when interval has passed."""
    updater = ProgressUpdater(progress_msg, min_interval=0.0)
    update = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/a.py"}}],
    )
    await updater.handle_update(update)
    progress_msg.edit_text.assert_called_once()
