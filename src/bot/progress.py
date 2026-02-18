"""Live progress updater for Telegram messages.

Receives StreamUpdate events from Claude's streaming infrastructure,
queues them, and periodically flushes a rolling log into a single
Telegram message via editMessageText.
"""

import time
from typing import Any, List

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

_MAX_MESSAGE_LEN = 3500  # Leave room under Telegram's 4096 limit
_MAX_CONTEXT_LEN = 60  # Truncate file paths / commands to this length


def _format_step(tool_name: str, tool_input: dict) -> str:  # type: ignore[type-arg]
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

    def __init__(self, message: Any, *, min_interval: float = 3.0) -> None:
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
            await self._auto_flush()

    async def _auto_flush(self) -> None:
        """Attempt to flush, respecting rate limit. Used by handle_update."""
        if not self._dirty:
            return

        now = time.monotonic()
        # First flush always fires immediately; subsequent ones are rate-limited
        if self._last_flush > 0.0 and now - self._last_flush < self._min_interval:
            return  # Rate limited

        self._last_flush = now
        self._dirty = False

        text = self._render()
        try:
            await self._message.edit_text(text)
        except Exception as e:
            logger.debug("Progress message edit failed", error=str(e))

    async def flush(self) -> None:
        """Edit the Telegram message with current steps (if rate limit allows)."""
        if not self._dirty:
            return

        now = time.monotonic()
        # Rate limit: skip if a previous flush happened recently
        if self._last_flush > 0.0 and now - self._last_flush < self._min_interval:
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
            keep: List[str] = []
            remaining = _MAX_MESSAGE_LEN - len(header) - 40  # Room for "...N earlier"
            for step in reversed(lines):
                if remaining - len(step) - 1 < 0:
                    break
                keep.insert(0, step)
                remaining -= len(step) + 1

            skipped = total - len(keep)
            truncation = (
                f"\u251c ...{skipped} earlier step{'s' if skipped != 1 else ''}\n"
            )
            full = header + truncation + "\n".join(keep)

        return full
