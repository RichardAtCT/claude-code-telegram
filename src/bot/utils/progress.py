"""Rich progress tracking for Claude stream callbacks.

Detects the current work stage based on tool calls and provides
formatted progress messages with elapsed time and stage indicators.
"""

import time
from enum import Enum
from typing import Dict, Optional, Tuple


class Stage(str, Enum):
    """Ordered work stages for Claude task execution."""

    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    CODING = "coding"
    TESTING = "testing"
    REVIEWING = "reviewing"
    FINALIZING = "finalizing"


# Tool name -> stage mapping
_TOOL_STAGE_MAP: Dict[str, Stage] = {
    "Grep": Stage.ANALYZING,
    "Glob": Stage.ANALYZING,
    "Read": Stage.ANALYZING,
    "LS": Stage.ANALYZING,
    "WebFetch": Stage.ANALYZING,
    "WebSearch": Stage.ANALYZING,
    "NotebookRead": Stage.ANALYZING,
    "TodoRead": Stage.ANALYZING,
    "Write": Stage.CODING,
    "Edit": Stage.CODING,
    "MultiEdit": Stage.CODING,
    "NotebookEdit": Stage.CODING,
    "TodoWrite": Stage.CODING,
}

# Stage display info: (emoji, english_label, chinese_label)
_STAGE_DISPLAY: Dict[Stage, Tuple[str, str, str]] = {
    Stage.INITIALIZING: ("\u2699\ufe0f", "Initializing...", "\u521d\u59cb\u5316\u4e2d..."),
    Stage.ANALYZING: ("\U0001f50d", "Analyzing code...", "\u5206\u6790\u4ee3\u78bc\u4e2d..."),
    Stage.CODING: ("\u270f\ufe0f", "Writing code...", "\u7de8\u5beb\u4ee3\u78bc\u4e2d..."),
    Stage.TESTING: ("\U0001f9ea", "Running tests...", "\u57f7\u884c\u6e2c\u8a66\u4e2d..."),
    Stage.REVIEWING: ("\U0001f9d0", "Reviewing...", "\u5be9\u67e5\u4e2d..."),
    Stage.FINALIZING: ("\u2705", "Finalizing...", "\u5b8c\u6210\u4e2d..."),
}

# Bash commands that indicate test execution
_TEST_COMMANDS = {"test", "pytest", "jest", "vitest", "mocha", "cargo test", "go test"}


def _is_test_command(command: str) -> bool:
    """Check if a bash command looks like a test invocation."""
    cmd_lower = command.lower()
    for test_cmd in _TEST_COMMANDS:
        if test_cmd in cmd_lower:
            return True
    # npm/yarn/pnpm test variants
    if any(
        pattern in cmd_lower
        for pattern in ["npm test", "npm run test", "yarn test", "pnpm test"]
    ):
        return True
    return False


class ProgressTracker:
    """Track progress stages during a Claude streaming session.

    Detects the current work stage based on which tools Claude is
    calling and how much time has elapsed since the last code-related
    tool call. Provides formatted status strings in English and Chinese.
    """

    def __init__(self, start_time: Optional[float] = None) -> None:
        self._start_time = start_time or time.time()
        self._current_stage = Stage.INITIALIZING
        self._last_coding_time: Optional[float] = None
        self._tool_count = 0
        # Seconds of no tool activity after coding before switching to REVIEWING
        self._review_delay = 5.0

    @property
    def current_stage(self) -> Stage:
        return self._current_stage

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time

    def update_stage(
        self, tool_name: str, tool_input: Optional[Dict] = None
    ) -> Tuple[Stage, str, str]:
        """Update the stage based on a new tool call.

        Returns:
            (stage, emoji, english_message)
        """
        self._tool_count += 1

        # Special case: Bash with test commands
        if tool_name == "Bash" and tool_input:
            cmd = tool_input.get("command", "")
            if _is_test_command(cmd):
                self._current_stage = Stage.TESTING
                return self._stage_info()

        # Check static mapping
        mapped = _TOOL_STAGE_MAP.get(tool_name)
        if mapped is not None:
            self._current_stage = mapped
            if mapped == Stage.CODING:
                self._last_coding_time = time.time()
            return self._stage_info()

        # Bash (non-test) after coding -> could be reviewing build output
        if tool_name == "Bash" and self._current_stage == Stage.CODING:
            self._current_stage = Stage.REVIEWING
            return self._stage_info()

        # Task/TaskOutput -> keep current or move to analyzing
        if tool_name in ("Task", "TaskOutput"):
            if self._current_stage == Stage.INITIALIZING:
                self._current_stage = Stage.ANALYZING
            return self._stage_info()

        return self._stage_info()

    def check_review_transition(self) -> bool:
        """Check if enough idle time has passed after coding to switch to REVIEWING.

        Call this periodically (e.g. on each throttled progress update).
        Returns True if the stage changed.
        """
        if (
            self._current_stage == Stage.CODING
            and self._last_coding_time is not None
            and (time.time() - self._last_coding_time) > self._review_delay
        ):
            self._current_stage = Stage.REVIEWING
            return True
        return False

    def format_progress(self, lang: str = "en") -> str:
        """Return a formatted progress string with elapsed time.

        Args:
            lang: "en" for English, "zh" for Chinese.

        Example outputs:
            "🔍 Analyzing code... (15s)"
            "🔍 分析代碼中... (15s)"
        """
        elapsed_s = int(self.elapsed)
        emoji, en_label, zh_label = _STAGE_DISPLAY[self._current_stage]
        label = zh_label if lang == "zh" else en_label
        return f"{emoji} {label} ({elapsed_s}s)"

    def _stage_info(self) -> Tuple[Stage, str, str]:
        """Return current stage info as (stage, emoji, english_label)."""
        emoji, en_label, _zh = _STAGE_DISPLAY[self._current_stage]
        return self._current_stage, emoji, en_label
