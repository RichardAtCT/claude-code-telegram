"""Claude-specific exceptions."""

from typing import List, Optional


class ClaudeError(Exception):
    """Base Claude error."""


class ClaudeTimeoutError(ClaudeError):
    """Operation timed out."""


class ClaudeProcessError(ClaudeError):
    """Process execution failed."""


class ClaudeParsingError(ClaudeError):
    """Failed to parse output."""


class ClaudeSessionError(ClaudeError):
    """Session management error."""


class ClaudeMCPError(ClaudeError):
    """MCP server connection or configuration error."""

    def __init__(self, message: str, server_name: Optional[str] = None):
        super().__init__(message)
        self.server_name = server_name


class ClaudeToolValidationError(ClaudeError):
    """Tool validation failed during Claude execution."""

    def __init__(
        self,
        message: str,
        blocked_tools: Optional[List[str]] = None,
        allowed_tools: Optional[List[str]] = None,
    ):
        super().__init__(message)
        self.blocked_tools = blocked_tools or []
        self.allowed_tools = allowed_tools or []
