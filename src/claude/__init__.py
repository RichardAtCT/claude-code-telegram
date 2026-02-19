"""Claude Code integration module."""

from .exceptions import (
    ClaudeError,
    ClaudeParsingError,
    ClaudeProcessError,
    ClaudeSessionError,
    ClaudeTimeoutError,
)
from .facade import ClaudeIntegration
from .integration import ClaudeProcessManager, ClaudeResponse, StreamUpdate
from .monitor import ToolMonitor
from .parser import OutputParser, ResponseFormatter
from .session import (
    ClaudeSession,
    InMemorySessionStorage,
    SessionManager,
    SessionStorage,
)
from .worktree import WorktreeError, WorktreeManager

__all__ = [
    # Exceptions
    "ClaudeError",
    "ClaudeParsingError",
    "ClaudeProcessError",
    "ClaudeSessionError",
    "ClaudeTimeoutError",
    # Main integration
    "ClaudeIntegration",
    # Core components
    "ClaudeProcessManager",
    "ClaudeResponse",
    "StreamUpdate",
    "SessionManager",
    "SessionStorage",
    "InMemorySessionStorage",
    "ClaudeSession",
    "ToolMonitor",
    "OutputParser",
    "ResponseFormatter",
    # Worktree
    "WorktreeManager",
    "WorktreeError",
]
