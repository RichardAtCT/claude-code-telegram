"""Bash directory boundary enforcement for Claude tool calls.

Provides the check_bash_directory_boundary() function used by the SDK's
can_use_tool callback to prevent filesystem-modifying commands from
operating outside the approved directory.
"""

import shlex
from pathlib import Path
from typing import Optional, Set, Tuple

import structlog

logger = structlog.get_logger()

# Commands that modify the filesystem and should have paths checked
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


def check_bash_directory_boundary(
    command: str,
    working_directory: Path,
    approved_directory: Path,
) -> Tuple[bool, Optional[str]]:
    """Check if a bash command's absolute paths stay within the approved directory.

    Returns (True, None) if the command is safe, or (False, error_message) if it
    attempts to write outside the approved directory boundary.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # If we can't parse the command, let it through —
        # the sandbox will catch it at the OS level
        return True, None

    if not tokens:
        return True, None

    base_command = Path(tokens[0]).name

    # Read-only commands are always allowed
    if base_command in _READ_ONLY_COMMANDS:
        return True, None

    # Handle ``find`` specially: only dangerous when it contains mutating actions
    if base_command == "find":
        has_mutating_action = any(t in _FIND_MUTATING_ACTIONS for t in tokens[1:])
        if not has_mutating_action:
            return True, None
        # Fall through to path checking below
    elif base_command not in _FS_MODIFYING_COMMANDS:
        # Only check filesystem-modifying commands
        return True, None

    # Check each argument for paths outside the boundary
    resolved_approved = approved_directory.resolve()

    for token in tokens[1:]:
        # Skip flags
        if token.startswith("-"):
            continue

        # Resolve both absolute and relative paths against the working
        # directory so that traversal sequences like ``../../evil`` are
        # caught instead of being silently allowed.
        if token.startswith("/"):
            resolved = Path(token).resolve()
        else:
            resolved = (working_directory / token).resolve()

        try:
            resolved.relative_to(resolved_approved)
        except ValueError:
            return False, (
                f"Directory boundary violation: '{base_command}' targets "
                f"'{token}' which is outside approved directory "
                f"'{resolved_approved}'"
            )

    return True, None
