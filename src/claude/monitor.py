"""Monitor Claude's tool usage.

Features:
- Track tool calls
- Security validation
- Usage analytics
- Bash directory boundary enforcement
"""

import shlex
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from ..config.settings import Settings
from ..security.validators import SecurityValidator



logger = structlog.get_logger()

# Commands that modify the filesystem or change context and should have paths checked
_FS_MODIFYING_COMMANDS: Set[str] = {
    "mkdir",
    "touch",
    "cp",
    "mv",
    "rm",
    "rmdir",
    "ln",
    "install",
    "tee",
    "cd",
}

# Commands that are read-only or don't take filesystem paths
_READ_ONLY_COMMANDS: Set[str] = {
    "cat",
    "ls",
    "head",
    "tail",
    "less",
    "more",
    "which",
    "whoami",
    "pwd",
    "echo",
    "printf",
    "env",
    "printenv",
    "date",
    "wc",
    "sort",
    "uniq",
    "diff",
    "file",
    "stat",
    "du",
    "df",
    "tree",
    "realpath",
    "dirname",
    "basename",
}

# Actions / expressions that make ``find`` a filesystem-modifying command
_FIND_MUTATING_ACTIONS: Set[str] = {"-delete", "-exec", "-execdir", "-ok", "-okdir"}

# Bash command separators
_COMMAND_SEPARATORS: Set[str] = {"&&", "||", ";", "|", "&"}


def check_bash_directory_boundary(
    command: str,
    working_directory: Path,
    approved_directory: Path,
) -> Tuple[bool, Optional[str]]:
    """Check if a bash command's absolute paths stay within the approved directory.

    This function parses the command string (including chained commands) and
    verifies that any filesystem-modifying or context-changing command (like cd)
    only targets paths within the approved boundary.

    Returns (True, None) if the command is safe, or (False, error_message) if it
    attempts to operate outside the approved directory boundary.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # If we can't parse the command, let it through —
        # the sandbox will catch it at the OS level
        return True, None

    if not tokens:
        return True, None

    # Split tokens into individual commands based on separators
    command_chains: List[List[str]] = []
    current_chain: List[str] = []

    for token in tokens:
        if token in _COMMAND_SEPARATORS:
            if current_chain:
                command_chains.append(current_chain)
            current_chain = []
        else:
            current_chain.append(token)

    if current_chain:
        command_chains.append(current_chain)

    resolved_approved = approved_directory.resolve()

    # Check each command in the chain
    for cmd_tokens in command_chains:
        if not cmd_tokens:
            continue

        base_command = Path(cmd_tokens[0]).name

        # Read-only commands are always allowed
        if base_command in _READ_ONLY_COMMANDS:
            continue

        # Determine if this specific command in the chain needs path validation
        needs_check = False
        if base_command == "find":
            needs_check = any(t in _FIND_MUTATING_ACTIONS for t in cmd_tokens[1:])
        elif base_command in _FS_MODIFYING_COMMANDS:
            needs_check = True

        if not needs_check:
            continue

        # Check each argument for paths outside the boundary
        for token in cmd_tokens[1:]:
            # Skip flags
            if token.startswith("-"):
                continue

            # Resolve both absolute and relative paths against the working
            # directory so that traversal sequences like ``../../evil`` are
            # caught instead of being silently allowed.
            try:
                if token.startswith("/"):
                    resolved = Path(token).resolve()
                else:
                    resolved = (working_directory / token).resolve()

                if not _is_within_directory(resolved, resolved_approved):
                    return False, (
                        f"Directory boundary violation: '{base_command}' targets "
                        f"'{token}' which is outside approved directory "
                        f"'{resolved_approved}'"
                    )
            except (ValueError, OSError):
                # If path resolution fails, the command might be malformed or
                # using bash features we can't statically analyze.
                # We skip checking this token and rely on the OS-level sandbox.
                continue

    return True, None


def _is_within_directory(path: Path, directory: Path) -> bool:
    """Check if path is within directory."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


class ToolMonitor:
    """Monitor and validate Claude's tool usage."""

    def __init__(
        self,
        config: Settings,
        security_validator: Optional[SecurityValidator] = None,
        agentic_mode: bool = False,
    ):
        """Initialize tool monitor."""
        self.config = config
        self.security_validator = security_validator
        self.agentic_mode = agentic_mode
        self.tool_usage: Dict[str, int] = defaultdict(int)
        self.security_violations: List[Dict[str, Any]] = []
        self.disable_tool_validation = getattr(config, "disable_tool_validation", False)

    async def validate_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        working_directory: Path,
        user_id: int,
    ) -> Tuple[bool, Optional[str]]:
        """Validate tool call before execution."""
        logger.debug(
            "Validating tool call",
            tool_name=tool_name,
            working_directory=str(working_directory),
            user_id=user_id,
        )

        # When disabled, skip only allowlist/disallowlist name checks.
        # Keep path and command safety validation active.
        if self.disable_tool_validation:
            logger.debug(
                "Tool name validation disabled; skipping allow/disallow checks",
                tool_name=tool_name,
                user_id=user_id,
            )

        # Check if tool is allowed
        if (
            not self.disable_tool_validation
            and hasattr(self.config, "claude_allowed_tools")
            and self.config.claude_allowed_tools
        ):
            if tool_name not in self.config.claude_allowed_tools:
                violation = {
                    "type": "disallowed_tool",
                    "tool_name": tool_name,
                    "user_id": user_id,
                    "working_directory": str(working_directory),
                }
                self.security_violations.append(violation)
                logger.warning("Tool not allowed", **violation)
                return False, f"Tool not allowed: {tool_name}"

        # Check if tool is explicitly disallowed
        if (
            not self.disable_tool_validation
            and hasattr(self.config, "claude_disallowed_tools")
            and self.config.claude_disallowed_tools
        ):
            if tool_name in self.config.claude_disallowed_tools:
                violation = {
                    "type": "explicitly_disallowed_tool",
                    "tool_name": tool_name,
                    "user_id": user_id,
                    "working_directory": str(working_directory),
                }
                self.security_violations.append(violation)
                logger.warning("Tool explicitly disallowed", **violation)
                return False, f"Tool explicitly disallowed: {tool_name}"

        # Validate file operations
        if tool_name in [
            "create_file",
            "edit_file",
            "read_file",
            "Write",
            "Edit",
            "Read",
        ]:
            file_path = tool_input.get("path") or tool_input.get("file_path")
            if not file_path:
                return False, "File path required"

            # Validate path security
            if self.security_validator:
                valid, resolved_path, error = self.security_validator.validate_path(
                    file_path, working_directory
                )

                if not valid:
                    violation = {
                        "type": "invalid_file_path",
                        "tool_name": tool_name,
                        "file_path": file_path,
                        "user_id": user_id,
                        "working_directory": str(working_directory),
                        "error": error,
                    }
                    self.security_violations.append(violation)
                    logger.warning("Invalid file path in tool call", **violation)
                    return False, error

        # Validate shell commands (skip in agentic mode — Claude Code runs
        # inside its own sandbox, and these patterns block normal gh/git usage)
        if tool_name in ["bash", "shell", "Bash"] and not self.agentic_mode:
            command = tool_input.get("command", "")

            # Check for dangerous commands
            dangerous_patterns = [
                "rm -rf",
                "sudo",
                "chmod 777",
                "curl",
                "wget",
                "nc ",
                "netcat",
                ">",
                ">>",
                "|",
                "&",
                ";",
                "$(",
                "`",
            ]

            for pattern in dangerous_patterns:
                if pattern in command.lower():
                    violation = {
                        "type": "dangerous_command",
                        "tool_name": tool_name,
                        "command": command,
                        "pattern": pattern,
                        "user_id": user_id,
                        "working_directory": str(working_directory),
                    }
                    self.security_violations.append(violation)
                    logger.warning("Dangerous command detected", **violation)
                    return False, f"Dangerous command pattern detected: {pattern}"

            # Check directory boundary for filesystem-modifying commands
            valid, error = check_bash_directory_boundary(
                command, working_directory, self.config.approved_directory
            )
            if not valid:
                violation = {
                    "type": "directory_boundary_violation",
                    "tool_name": tool_name,
                    "command": command,
                    "user_id": user_id,
                    "working_directory": str(working_directory),
                    "error": error,
                }
                self.security_violations.append(violation)
                logger.warning("Directory boundary violation", **violation)
                return False, error

        # Track usage
        self.tool_usage[tool_name] += 1

        logger.debug("Tool call validated successfully", tool_name=tool_name)
        return True, None

    def get_tool_stats(self) -> Dict[str, Any]:
        """Get tool usage statistics."""
        return {
            "total_calls": sum(self.tool_usage.values()),
            "by_tool": dict(self.tool_usage),
            "unique_tools": len(self.tool_usage),
            "security_violations": len(self.security_violations),
        }

    def get_security_violations(self) -> List[Dict[str, Any]]:
        """Get security violations."""
        return self.security_violations.copy()

    def reset_stats(self) -> None:
        """Reset statistics."""
        self.tool_usage.clear()
        self.security_violations.clear()
        logger.info("Tool monitor statistics reset")

    def get_user_tool_usage(self, user_id: int) -> Dict[str, Any]:
        """Get tool usage for specific user."""
        user_violations = [
            v for v in self.security_violations if v.get("user_id") == user_id
        ]

        return {
            "user_id": user_id,
            "security_violations": len(user_violations),
            "violation_types": list(set(v.get("type") for v in user_violations)),
        }

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if tool is allowed without validation."""
        # Check allowed list
        if (
            hasattr(self.config, "claude_allowed_tools")
            and self.config.claude_allowed_tools
        ):
            if tool_name not in self.config.claude_allowed_tools:
                return False

        # Check disallowed list
        if (
            hasattr(self.config, "claude_disallowed_tools")
            and self.config.claude_disallowed_tools
        ):
            if tool_name in self.config.claude_disallowed_tools:
                return False

        return True
