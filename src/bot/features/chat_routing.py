"""Per-chat routing: working directories and group conversation history buffer.

This module enables two related features:

**Per-chat working directories**
Map specific Telegram chat IDs to dedicated Claude sessions and working
directories via ``PERSONAL_CHAT_ID`` / ``PERSONAL_CHAT_DIRECTORY`` and
``GROUP_CHAT_ID`` / ``GROUP_CHAT_DIRECTORY`` in your ``.env``.  Messages from
an unrecognised chat fall back to ``APPROVED_DIRECTORY``.

**Group trigger prefix + conversation history**
In group chats Claude is silent by default.  Only messages that begin with
the configured prefix (default: ``claude``) — or the equivalent slash command
(``/claude``) — trigger a response.  All other messages are stored in a
per-chat rolling buffer so that when Claude *is* triggered it receives the
recent conversation as context, allowing it to answer questions about what
was discussed without every participant having to @-mention the bot.
"""

from pathlib import Path
from typing import Any, Dict, List

# Maximum number of messages kept in the per-chat history buffer.
MAX_BUFFER_SIZE = 30

# How many buffered messages are prepended as context when Claude is triggered.
HISTORY_CONTEXT_SIZE = 20


class GroupChatBuffer:
    """Rolling buffer of recent group chat messages, stored in ``chat_data``.

    Each entry is a ``{"sender": str, "text": str}`` dict.  The buffer is
    capped at :data:`MAX_BUFFER_SIZE` entries; older messages are evicted from
    the front as new ones arrive.

    All methods are static so callers can pass a plain list from
    ``context.chat_data`` without instantiating the class.
    """

    @staticmethod
    def append(buffer: List[Dict[str, Any]], sender_name: str, text: str) -> None:
        """Append a message and trim the buffer to :data:`MAX_BUFFER_SIZE`."""
        buffer.append({"sender": sender_name, "text": text})
        if len(buffer) > MAX_BUFFER_SIZE:
            del buffer[: len(buffer) - MAX_BUFFER_SIZE]

    @staticmethod
    def format_history(messages: List[Dict[str, Any]]) -> str:
        """Return messages formatted as ``Sender: text`` lines."""
        lines = []
        for msg in messages:
            sender = msg.get("sender", "Unknown")
            text = msg.get("text", "")
            lines.append(f"{sender}: {text}")
        return "\n".join(lines)


def get_working_directory(chat_id: int, settings: Any) -> Path:
    """Return the working directory to use for *chat_id*.

    Priority:
    1. ``personal_chat_directory`` if ``chat_id == personal_chat_id``
    2. ``group_chat_directory`` if ``chat_id == group_chat_id``
    3. ``approved_directory`` (the global fallback)
    """
    if (
        settings.personal_chat_id is not None
        and chat_id == settings.personal_chat_id
        and settings.personal_chat_directory is not None
    ):
        return settings.personal_chat_directory
    if (
        settings.group_chat_id is not None
        and chat_id == settings.group_chat_id
        and settings.group_chat_directory is not None
    ):
        return settings.group_chat_directory
    return settings.approved_directory
