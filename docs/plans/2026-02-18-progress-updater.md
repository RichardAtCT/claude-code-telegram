# Progress Updater — Edit-in-Place Streaming Updates

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the static "Working..." message with a live-updating rolling log of what Claude is doing, using Telegram's `editMessageText` API.

**Architecture:** A new `ProgressUpdater` class receives `StreamUpdate` events from the existing streaming infrastructure, queues them, and flushes them into a single Telegram message every 3 seconds. The orchestrator creates the updater and passes its callback to `run_command(on_stream=...)`. No changes to facade, SDK backend, or CLI backend — they already emit the events.

**Tech Stack:** Python 3.10+, python-telegram-bot, asyncio, structlog

---

### Task 1: Create `ProgressUpdater` class

**Files:**
- Create: `src/bot/progress.py`
- Test: `tests/unit/test_bot/test_progress.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_bot/__init__.py` (empty, if it doesn't exist) and `tests/unit/test_bot/test_progress.py`:

```python
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


async def test_single_tool_call_queued_and_flushed(updater, progress_msg):
    """A single tool call is queued and rendered on flush."""
    update = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/src/main.py"}}],
    )
    await updater.handle_update(update)
    await updater.flush()

    progress_msg.edit_text.assert_called_once()
    text = progress_msg.edit_text.call_args.args[0]
    assert "Reading" in text
    assert "main.py" in text


async def test_multiple_tools_queued_all_shown(updater, progress_msg):
    """Multiple tool calls all appear in the flushed message."""
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

    await updater.flush()

    text = progress_msg.edit_text.call_args.args[0]
    assert "Reading" in text
    assert "Running" in text
    assert "Editing" in text


async def test_rate_limiting_skips_rapid_flushes(updater, progress_msg):
    """Flush is skipped if called within the min_interval."""
    update = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/a.py"}}],
    )
    await updater.handle_update(update)
    await updater.flush()
    assert progress_msg.edit_text.call_count == 1

    # Immediate second flush — should be skipped (rate limited)
    update2 = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Write", "input": {"file_path": "/b.py"}}],
    )
    await updater.handle_update(update2)
    await updater.flush()
    assert progress_msg.edit_text.call_count == 1  # Still 1 — rate limited


async def test_flush_after_interval_succeeds(updater, progress_msg):
    """Flush succeeds after the rate limit interval passes."""
    updater._min_interval = 0.0  # Disable rate limiting for this test

    update1 = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Read", "input": {"file_path": "/a.py"}}],
    )
    await updater.handle_update(update1)
    await updater.flush()
    assert progress_msg.edit_text.call_count == 1

    update2 = StreamUpdate(
        type="assistant",
        tool_calls=[{"name": "Write", "input": {"file_path": "/b.py"}}],
    )
    await updater.handle_update(update2)
    await updater.flush()
    assert progress_msg.edit_text.call_count == 2


async def test_truncation_when_too_many_steps(updater, progress_msg):
    """Old steps are truncated when the message would exceed Telegram limits."""
    # Add many steps
    for i in range(60):
        update = StreamUpdate(
            type="assistant",
            tool_calls=[{"name": "Read", "input": {"file_path": f"/file_{i}.py"}}],
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
        assert expected_label.lower() in text.lower(), (
            f"Tool {tool_name} should map to label containing '{expected_label}'"
        )


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
    # With min_interval=0.0, handle_update should have auto-flushed
    progress_msg.edit_text.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_bot/test_progress.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.bot.progress'`

**Step 3: Write the implementation**

Create `src/bot/progress.py`:

```python
"""Live progress updater for Telegram messages.

Receives StreamUpdate events from Claude's streaming infrastructure,
queues them, and periodically flushes a rolling log into a single
Telegram message via editMessageText.
"""

import asyncio
import time
from typing import List, Optional

import structlog

from ..claude.integration import StreamUpdate

logger = structlog.get_logger()

# Tool name -> (human-friendly verb, input key to extract short context)
_TOOL_LABELS = {
    "Read": ("Reading", "file_path"),
    "Write": ("Writing", "file_path"),
    "Edit": ("Editing", "file_path"),
    "MultiEdit": ("Editing", "file_path"),
    "Bash": ("Running command", "command"),
    "Grep": ("Searching code", "pattern"),
    "Glob": ("Finding files", "pattern"),
    "WebFetch": ("Fetching URL", "url"),
    "WebSearch": ("Searching web", "query"),
    "Task": ("Running subtask", "prompt"),
    "LS": ("Listing files", "path"),
    "NotebookRead": ("Reading notebook", "notebook_path"),
    "NotebookEdit": ("Editing notebook", "notebook_path"),
    "TodoRead": ("Reading todos", None),
    "TodoWrite": ("Updating todos", None),
}

_MAX_MESSAGE_LEN = 4000  # Leave room under Telegram's 4096 limit
_MAX_CONTEXT_LEN = 60  # Truncate file paths / commands to this length


def _format_step(tool_name: str, tool_input: dict) -> str:
    """Turn a tool call into a human-readable step line."""
    label, input_key = _TOOL_LABELS.get(tool_name, (tool_name, None))

    context = ""
    if input_key and input_key in tool_input:
        raw = str(tool_input[input_key])
        # For file paths, just show the basename or last component
        if input_key in ("file_path", "notebook_path", "path"):
            raw = raw.rsplit("/", 1)[-1] if "/" in raw else raw
        # For commands, show first line only
        if input_key == "command":
            raw = raw.split("\n")[0]
        if len(raw) > _MAX_CONTEXT_LEN:
            raw = raw[:_MAX_CONTEXT_LEN] + "..."
        context = f" {raw}"

    return f"{label}{context}"


class ProgressUpdater:
    """Edits a single Telegram message with a rolling log of Claude's actions.

    Usage::

        progress_msg = await msg.reply_text("Working...")
        updater = ProgressUpdater(progress_msg)
        response = await claude.run_command(..., on_stream=updater.handle_update)
        await updater.stop()
    """

    def __init__(self, message: object, *, min_interval: float = 3.0) -> None:
        self._message = message  # Telegram Message with edit_text()
        self._min_interval = min_interval
        self._steps: List[str] = []
        self._last_flush: float = 0.0
        self._dirty = False

    async def handle_update(self, update: StreamUpdate) -> None:
        """Receive a StreamUpdate and queue any tool-call steps."""
        if update.tool_calls:
            for call in update.tool_calls:
                name = call.get("name", "")
                inp = call.get("input", {})
                step = _format_step(name, inp)
                self._steps.append(step)
                self._dirty = True

        # Auto-flush if enough time has passed
        if self._dirty:
            await self.flush()

    async def flush(self) -> None:
        """Edit the Telegram message with current steps (if rate limit allows)."""
        if not self._dirty:
            return

        now = time.monotonic()
        if now - self._last_flush < self._min_interval:
            return  # Rate limited — will flush on next call

        self._last_flush = now
        self._dirty = False

        text = self._render()
        try:
            await self._message.edit_text(text)
        except Exception as e:
            logger.debug("Progress message edit failed", error=str(e))

    async def stop(self) -> None:
        """Final flush — ignores rate limit to ensure last state is shown."""
        if self._dirty:
            self._last_flush = 0.0  # Reset to bypass rate limit
            await self.flush()

    def _render(self) -> str:
        """Build the message text from accumulated steps."""
        total = len(self._steps)
        header = f"\u23f3 Working... ({total} step{'s' if total != 1 else ''})\n"

        # Build lines bottom-up — newest at the end
        lines = []
        for i, step in enumerate(self._steps):
            connector = "\u2514" if i == total - 1 else "\u251c"
            lines.append(f"{connector} {step}")

        body = "\n".join(lines)
        full = header + body

        # Truncate oldest if too long
        if len(full) > _MAX_MESSAGE_LEN:
            # Keep header + newest steps that fit
            keep = []
            remaining = _MAX_MESSAGE_LEN - len(header) - 40  # Room for "...N earlier"
            for step in reversed(lines):
                if remaining - len(step) - 1 < 0:
                    break
                keep.insert(0, step)
                remaining -= len(step) + 1

            skipped = total - len(keep)
            truncation = f"\u251c ...{skipped} earlier step{'s' if skipped != 1 else ''}\n"
            full = header + truncation + "\n".join(keep)

        return full
```

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/unit/test_bot/test_progress.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/bot/progress.py tests/unit/test_bot/__init__.py tests/unit/test_bot/test_progress.py
git commit -m "feat: add ProgressUpdater for live Telegram status updates"
```

---

### Task 2: Fix SDK streaming to emit tool_calls in StreamUpdate

**Files:**
- Modify: `src/claude/sdk_integration.py:375-416` (`_handle_stream_message`)
- Test: `tests/unit/test_claude/test_sdk_integration.py` (add test)

The SDK's `_handle_stream_message` currently only emits text content for `AssistantMessage`. It skips `ToolUseBlock` objects entirely (line 403-404 is a TODO comment). The `ProgressUpdater` needs `tool_calls` in the `StreamUpdate` to work. The CLI backend already does this correctly.

**Step 1: Write the failing test**

Add to `tests/unit/test_claude/test_sdk_integration.py`:

```python
async def test_handle_stream_message_emits_tool_calls(sdk_manager):
    """_handle_stream_message should emit tool_calls for ToolUseBlock."""
    from unittest.mock import AsyncMock, MagicMock
    from claude_agent_sdk import AssistantMessage, ToolUseBlock

    callback = AsyncMock()

    # Create an AssistantMessage with a ToolUseBlock
    tool_block = MagicMock(spec=ToolUseBlock)
    tool_block.tool_name = "Read"
    tool_block.tool_input = {"file_path": "/test.py"}
    tool_block.id = "tool_123"

    message = MagicMock(spec=AssistantMessage)
    message.content = [tool_block]

    await sdk_manager._handle_stream_message(message, callback)

    callback.assert_called_once()
    update = callback.call_args.args[0]
    assert update.tool_calls is not None
    assert len(update.tool_calls) == 1
    assert update.tool_calls[0]["name"] == "Read"
    assert update.tool_calls[0]["input"] == {"file_path": "/test.py"}
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_claude/test_sdk_integration.py::test_handle_stream_message_emits_tool_calls -v`
Expected: FAIL — callback either not called or update has no tool_calls

**Step 3: Modify `_handle_stream_message` in `src/claude/sdk_integration.py`**

Replace the method body (lines 375-416) with:

```python
    async def _handle_stream_message(
        self, message: Message, stream_callback: Callable[[StreamUpdate], None]
    ) -> None:
        """Handle streaming message from claude-agent-sdk."""
        try:
            if isinstance(message, AssistantMessage):
                content = getattr(message, "content", [])
                if content and isinstance(content, list):
                    text_parts = []
                    tool_calls = []

                    for block in content:
                        if hasattr(block, "text"):
                            text_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            tool_calls.append(
                                {
                                    "name": getattr(block, "tool_name", "unknown"),
                                    "input": getattr(block, "tool_input", {}),
                                    "id": getattr(block, "id", None),
                                }
                            )

                    if text_parts or tool_calls:
                        update = StreamUpdate(
                            type="assistant",
                            content="\n".join(text_parts) if text_parts else None,
                            tool_calls=tool_calls if tool_calls else None,
                        )
                        await stream_callback(update)

                elif content:
                    update = StreamUpdate(
                        type="assistant",
                        content=str(content),
                    )
                    await stream_callback(update)

            elif isinstance(message, UserMessage):
                content = getattr(message, "content", "")
                if content:
                    update = StreamUpdate(
                        type="user",
                        content=content,
                    )
                    await stream_callback(update)

        except Exception as e:
            logger.warning("Stream callback failed", error=str(e))
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_claude/test_sdk_integration.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/claude/sdk_integration.py tests/unit/test_claude/test_sdk_integration.py
git commit -m "fix: emit tool_calls in SDK stream handler for progress tracking"
```

---

### Task 3: Wire ProgressUpdater into orchestrator

**Files:**
- Modify: `src/bot/orchestrator.py:226-362` (`agentic_text`)
- Modify: `src/bot/orchestrator.py:364-482` (`agentic_document`)
- Modify: `src/bot/orchestrator.py:484-552` (`agentic_photo`)
- Test: `tests/unit/test_orchestrator.py` (add test)

**Step 1: Write the failing test**

Add to `tests/unit/test_orchestrator.py`:

```python
async def test_agentic_text_passes_on_stream_callback(agentic_settings, deps):
    """agentic_text passes an on_stream callback to run_command."""
    orchestrator = MessageOrchestrator(agentic_settings, deps)

    mock_response = MagicMock()
    mock_response.session_id = "session-abc"
    mock_response.content = "Done!"
    mock_response.tools_used = []

    claude_integration = AsyncMock()
    claude_integration.run_command = AsyncMock(return_value=mock_response)

    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "fix the bug"
    update.message.message_id = 1
    update.message.chat.send_action = AsyncMock()
    update.message.reply_text = AsyncMock()

    progress_msg = AsyncMock()
    progress_msg.edit_text = AsyncMock()
    progress_msg.delete = AsyncMock()
    update.message.reply_text.return_value = progress_msg

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {
        "settings": agentic_settings,
        "claude_integration": claude_integration,
        "storage": None,
        "rate_limiter": None,
        "audit_logger": None,
    }

    await orchestrator.agentic_text(update, context)

    # run_command was called with an on_stream keyword argument
    call_kwargs = claude_integration.run_command.call_args.kwargs
    assert "on_stream" in call_kwargs
    assert call_kwargs["on_stream"] is not None
    assert callable(call_kwargs["on_stream"])
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_orchestrator.py::test_agentic_text_passes_on_stream_callback -v`
Expected: FAIL — `on_stream` not in call kwargs (currently not passed)

**Step 3: Modify `agentic_text` in `src/bot/orchestrator.py`**

Add import at top of file (after other imports):

```python
from .progress import ProgressUpdater
```

In `agentic_text()`, change the `run_command` call (lines 249 and 265-270). Replace:

```python
        progress_msg = await update.message.reply_text("Working...")
```

with:

```python
        progress_msg = await update.message.reply_text("\u23f3 Working...")
        progress = ProgressUpdater(progress_msg)
```

Replace:

```python
            claude_response = await claude_integration.run_command(
                prompt=message_text,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
            )
```

with:

```python
            claude_response = await claude_integration.run_command(
                prompt=message_text,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=progress.handle_update,
            )
```

Also add a final flush before deleting the progress message. Replace:

```python
        await progress_msg.delete()
```

with:

```python
        await progress.stop()
        await progress_msg.delete()
```

Apply the same pattern to `agentic_document` and `agentic_photo`:

In `agentic_document`, replace:

```python
        progress_msg = await update.message.reply_text("Working...")
```

with:

```python
        progress_msg = await update.message.reply_text("\u23f3 Working...")
        progress = ProgressUpdater(progress_msg)
```

Replace:

```python
            claude_response = await claude_integration.run_command(
                prompt=prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
            )
```

with:

```python
            claude_response = await claude_integration.run_command(
                prompt=prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=progress.handle_update,
            )
```

And before `await progress_msg.delete()`, add `await progress.stop()`.

In `agentic_photo`, same pattern: replace `"Working..."` with `"\u23f3 Working..."`, create `ProgressUpdater`, pass `on_stream=progress.handle_update`, and add `await progress.stop()` before delete.

**Step 4: Run all tests to verify they pass**

Run: `poetry run pytest tests/unit/test_orchestrator.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/bot/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat: wire ProgressUpdater into agentic handlers for live updates"
```

---

### Task 4: Run full test suite and lint

**Step 1: Run full test suite**

Run: `poetry run pytest tests/ -v --tb=short`
Expected: All PASS

**Step 2: Run linter**

Run: `poetry run black src/bot/progress.py tests/unit/test_bot/test_progress.py src/bot/orchestrator.py src/claude/sdk_integration.py && poetry run isort src/bot/progress.py tests/unit/test_bot/test_progress.py src/bot/orchestrator.py src/claude/sdk_integration.py`

**Step 3: Run type checker**

Run: `poetry run mypy src/bot/progress.py src/bot/orchestrator.py src/claude/sdk_integration.py`

**Step 4: Fix any issues and commit**

```bash
git add -u
git commit -m "chore: lint and type fixes for progress updater"
```

---

### Task 5: Restart the systemd service and verify

**Step 1: Restart the bot**

Run: `systemctl restart claude-telegram-bot`

**Step 2: Check it started cleanly**

Run: `systemctl status claude-telegram-bot`
Expected: `active (running)`

**Step 3: Manual test**

Send a message to `@skavinski_dev_bot` on Telegram. Verify:
- The "Working..." message appears immediately
- It updates in-place to show tool steps as Claude works
- On completion, the progress message is deleted and replaced with the final response

**Step 4: Check logs for any errors**

Run: `journalctl -u claude-telegram-bot --since "1 min ago" --no-pager`
Expected: No errors related to progress updates
