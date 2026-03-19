"""Interactive confirmation for dangerous operations.

Intercepts potentially dangerous tool calls (rm -rf, git push --force, etc.)
and prompts the user for confirmation before proceeding.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = structlog.get_logger()

# Dangerous bash patterns: (compiled regex, human-readable risk description)
_DANGEROUS_BASH_PATTERNS: List[tuple] = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--recursive)\b", re.I), "Recursive file deletion"),
    (re.compile(r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b", re.I), "Recursive file deletion"),
    (re.compile(r"\bgit\s+push\s+.*--force\b", re.I), "Force push (may overwrite remote history)"),
    (re.compile(r"\bgit\s+push\s+-f\b", re.I), "Force push (may overwrite remote history)"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "Hard reset (discards uncommitted changes)"),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f", re.I), "Git clean (removes untracked files)"),
    (re.compile(r"\bdrop\s+(table|database|index)\b", re.I), "SQL DROP statement"),
    (re.compile(r"\btruncate\s+table\b", re.I), "SQL TRUNCATE statement"),
    (re.compile(r"\bdelete\s+from\b.*\bwhere\b.*[=<>]", re.I | re.S), None),  # DELETE with WHERE is less risky
    (re.compile(r"\bdelete\s+from\s+\S+\s*;?\s*$", re.I), "DELETE without WHERE clause"),
    (re.compile(r"\bsudo\b", re.I), "Command runs with elevated privileges (sudo)"),
    (re.compile(r"\bchmod\s+777\b"), "Setting world-writable permissions"),
    (re.compile(r"\bmkfs\b", re.I), "Filesystem format command"),
    (re.compile(r"\bdd\s+", re.I), "Low-level disk write (dd)"),
    (re.compile(r">\s*/dev/sd[a-z]", re.I), "Writing directly to disk device"),
    (re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b", re.I), "Piping remote script to shell"),
    (re.compile(r"\bwget\b.*\|\s*(ba)?sh\b", re.I), "Piping remote script to shell"),
]

# Sensitive file patterns for Write/Edit operations
_SENSITIVE_FILE_PATTERNS: List[tuple] = [
    (re.compile(r"\.env($|\.)"), "Environment file (.env)"),
    (re.compile(r"credentials", re.I), "Credentials file"),
    (re.compile(r"secrets?\.ya?ml$", re.I), "Secrets configuration"),
    (re.compile(r"\.pem$", re.I), "PEM certificate/key"),
    (re.compile(r"\.key$", re.I), "Private key file"),
    (re.compile(r"id_rsa", re.I), "SSH private key"),
    (re.compile(r"id_ed25519", re.I), "SSH private key"),
    (re.compile(r"\.ssh/config$", re.I), "SSH configuration"),
    (re.compile(r"/etc/(passwd|shadow|sudoers)", re.I), "System auth file"),
    (re.compile(r"docker-compose.*\.ya?ml$", re.I), "Docker Compose config"),
    (re.compile(r"Dockerfile$", re.I), None),  # Dockerfiles are OK
    (re.compile(r"\.kube/config$", re.I), "Kubernetes config"),
]


@dataclass
class PendingAction:
    """A pending action awaiting user confirmation."""

    confirmation_id: str
    user_id: int
    chat_id: int
    action_description: str
    tool_name: str
    tool_input: Dict[str, Any]
    created_at: datetime
    callback: Optional[Callable[..., Coroutine]] = field(default=None, repr=False)


class ConfirmationManager:
    """Manages interactive confirmations for dangerous operations."""

    def __init__(
        self,
        timeout_seconds: int = 60,
        extra_patterns: Optional[List[str]] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.pending: Dict[str, PendingAction] = {}
        self._extra_patterns: List[re.Pattern] = []
        if extra_patterns:
            for pat in extra_patterns:
                try:
                    self._extra_patterns.append(re.compile(pat, re.I))
                except re.error:
                    logger.warning("Invalid extra dangerous pattern", pattern=pat)

        logger.info(
            "ConfirmationManager initialized",
            timeout_seconds=timeout_seconds,
            extra_patterns_count=len(self._extra_patterns),
        )

    def is_dangerous(
        self, tool_name: str, tool_input: Dict[str, Any]
    ) -> Optional[str]:
        """Check if a tool call is potentially dangerous.

        Returns a human-readable risk description, or None if the operation
        looks safe.
        """
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            return self._check_bash_danger(command)

        if tool_name in ("Write", "Edit", "MultiEdit"):
            file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
            return self._check_file_danger(file_path, tool_name)

        return None

    def _check_bash_danger(self, command: str) -> Optional[str]:
        """Check a bash command for dangerous patterns."""
        if not command:
            return None

        for pattern, description in _DANGEROUS_BASH_PATTERNS:
            if pattern.search(command) and description:
                return description

        # Check extra user-configured patterns
        for pattern in self._extra_patterns:
            if pattern.search(command):
                return f"Matches custom dangerous pattern: {pattern.pattern}"

        return None

    def _check_file_danger(
        self, file_path: str, tool_name: str
    ) -> Optional[str]:
        """Check if writing/editing a file path is dangerous."""
        if not file_path:
            return None

        for pattern, description in _SENSITIVE_FILE_PATTERNS:
            if pattern.search(file_path) and description:
                return f"{description} ({tool_name})"

        return None

    async def request_confirmation(
        self,
        bot: Any,
        user_id: int,
        chat_id: int,
        action_desc: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        message_thread_id: Optional[int] = None,
    ) -> str:
        """Send a confirmation request to the user.

        Returns the confirmation_id (UUID).
        """
        self.cleanup_expired()

        confirmation_id = str(uuid.uuid4())

        pending = PendingAction(
            confirmation_id=confirmation_id,
            user_id=user_id,
            chat_id=chat_id,
            action_description=action_desc,
            tool_name=tool_name,
            tool_input=tool_input,
            created_at=datetime.now(UTC),
        )
        self.pending[confirmation_id] = pending

        # Build inline keyboard
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "\u2705 Approve",
                        callback_data=f"dangerous_confirm:{confirmation_id}:yes",
                    ),
                    InlineKeyboardButton(
                        "\u274c Deny",
                        callback_data=f"dangerous_confirm:{confirmation_id}:no",
                    ),
                ]
            ]
        )

        # Summarize what's about to happen
        tool_summary = self._summarize_tool(tool_name, tool_input)

        text = (
            "\u26a0\ufe0f <b>Confirmation Required</b>\n\n"
            f"<b>Risk:</b> {_escape_html(action_desc)}\n"
            f"<b>Tool:</b> <code>{_escape_html(tool_name)}</code>\n"
            f"<b>Detail:</b> <code>{_escape_html(tool_summary)}</code>\n\n"
            f"This action expires in {self.timeout_seconds}s."
        )

        kwargs: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }
        if message_thread_id:
            kwargs["message_thread_id"] = message_thread_id

        await bot.send_message(**kwargs)

        logger.info(
            "Confirmation requested",
            confirmation_id=confirmation_id,
            user_id=user_id,
            risk=action_desc,
            tool=tool_name,
        )

        return confirmation_id

    def handle_response(
        self, confirmation_id: str, approved: bool
    ) -> Optional[PendingAction]:
        """Process a user's approve/deny response.

        Returns the PendingAction if found (and removes it), or None if
        expired / not found.
        """
        self.cleanup_expired()

        pending = self.pending.pop(confirmation_id, None)
        if pending is None:
            logger.warning(
                "Confirmation not found or expired",
                confirmation_id=confirmation_id,
            )
            return None

        logger.info(
            "Confirmation response",
            confirmation_id=confirmation_id,
            approved=approved,
            tool=pending.tool_name,
        )
        return pending

    def cleanup_expired(self) -> int:
        """Remove entries older than timeout. Returns count removed."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.timeout_seconds)
        expired_ids = [
            cid
            for cid, action in self.pending.items()
            if action.created_at < cutoff
        ]
        for cid in expired_ids:
            del self.pending[cid]

        if expired_ids:
            logger.debug("Cleaned up expired confirmations", count=len(expired_ids))

        return len(expired_ids)

    @staticmethod
    def _summarize_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Short summary of the tool call for display."""
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            if len(cmd) > 120:
                return cmd[:120] + "..."
            return cmd
        if tool_name in ("Write", "Edit", "MultiEdit"):
            return tool_input.get("file_path", "") or tool_input.get("path", "")
        return str(tool_input)[:120]


def _escape_html(text: str) -> str:
    """Minimal HTML escape for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
