"""Stream partial responses to Telegram via sendMessageDraft.

Uses Telegram Bot API 9.3+ sendMessageDraft for smooth token-by-token
streaming in private chats. Falls back to editMessageText for group chats
where sendMessageDraft is unavailable.
"""

import secrets
import time
from typing import List, Optional

import structlog
import telegram

from src.utils.constants import TELEGRAM_MAX_MESSAGE_LENGTH

logger = structlog.get_logger()

# Max tool lines shown in the draft header
_MAX_TOOL_LINES = 10

# Minimum characters before sending the first draft (avoids triggering
# push notifications with just a few characters)
_MIN_INITIAL_CHARS = 20

# Error messages that indicate the draft transport is unavailable
_DRAFT_UNAVAILABLE_ERRORS = frozenset({
    "TEXTDRAFT_PEER_INVALID",
    "Bad Request: draft can't be sent",
    "Bad Request: peer doesn't support drafts",
})


def generate_draft_id() -> int:
    """Generate a non-zero positive draft ID.

    The same draft_id causes Telegram to animate text transitions instead of
    replacing the draft wholesale, giving a smooth streaming effect.
    """
    return secrets.randbits(30) | 1


class DraftStreamer:
    """Accumulates streamed text and sends periodic drafts to Telegram.

    The draft is composed of two sections:

    1. **Tool header** — compact lines showing tool calls and reasoning
       snippets as they arrive.
    2. **Response body** — the actual assistant response text, streamed
       token-by-token.

    Both sections are combined into a single draft message and sent via
    ``sendMessageDraft`` (private chats) or ``editMessageText`` (groups).

    Key design decisions (inspired by OpenClaw):
    - Plain text drafts (no parse_mode) to avoid partial HTML/markdown errors.
    - Tail-truncation for messages >4096 chars.
    - Min initial chars: waits for ~20 chars before first send.
    - Anti-regressive: skips updates where text got shorter.
    - Error classification: distinguishes draft-unavailable (fall back to edit)
      from other errors (disable entirely).
    - Self-disabling: persistent errors silently disable the streamer.
    """

    def __init__(
        self,
        bot: telegram.Bot,
        chat_id: int,
        draft_id: int,
        message_thread_id: Optional[int] = None,
        throttle_interval: float = 0.4,
        is_private_chat: bool = True,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.draft_id = draft_id
        self.message_thread_id = message_thread_id
        self.throttle_interval = throttle_interval

        self._tool_lines: List[str] = []
        self._accumulated_text = ""
        self._last_send_time = 0.0
        self._last_sent_length = 0  # anti-regressive tracking
        self._enabled = True
        self._error_count = 0
        self._max_errors = 3

        # Transport mode: "draft" for private chats, "edit" for groups
        self._use_draft = is_private_chat
        self._edit_message_id: Optional[int] = None  # for edit-based transport

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def append_tool(self, line: str) -> None:
        """Append a tool activity line and send a draft if throttled."""
        if not self._enabled or not line:
            return
        self._tool_lines.append(line)
        now = time.time()
        if (now - self._last_send_time) >= self.throttle_interval:
            await self._send_draft()

    async def append_text(self, text: str) -> None:
        """Append streamed text and send a draft if throttle interval elapsed."""
        if not self._enabled or not text:
            return
        self._accumulated_text += text
        now = time.time()
        if (now - self._last_send_time) >= self.throttle_interval:
            await self._send_draft()

    async def flush(self) -> None:
        """Force-send the current accumulated text as a draft."""
        if not self._enabled:
            return
        if not self._accumulated_text and not self._tool_lines:
            return
        await self._send_draft(force=True)

    def _compose_draft(self, is_final: bool = False) -> str:
        """Combine tool header and response body into a single draft.

        Appends a blinking cursor ▌ during streaming (like OpenClaw)
        to indicate the response is still being generated.
        """
        parts: List[str] = []

        if self._tool_lines:
            visible = self._tool_lines[-_MAX_TOOL_LINES:]
            overflow = len(self._tool_lines) - _MAX_TOOL_LINES
            if overflow >= 3:
                parts.append(f"... +{overflow} more")
            parts.extend(visible)

        if self._accumulated_text:
            if parts:
                parts.append("")  # blank separator line
            text = self._accumulated_text
            if not is_final:
                text += " ▌"
            parts.append(text)

        return "\n".join(parts)

    async def _send_draft(self, force: bool = False) -> None:
        """Send the composed draft via the appropriate transport."""
        draft_text = self._compose_draft()
        if not draft_text.strip():
            return

        # Min initial chars gate (skip if force-flushing)
        if not force and self._last_sent_length == 0:
            if len(self._accumulated_text) < _MIN_INITIAL_CHARS and not self._tool_lines:
                return

        # Anti-regressive: skip if text got shorter (can happen with
        # tool header rotation)
        current_len = len(draft_text)
        if not force and current_len < self._last_sent_length:
            return

        # Tail-truncate if over Telegram limit
        if len(draft_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            draft_text = "\u2026" + draft_text[-(TELEGRAM_MAX_MESSAGE_LENGTH - 1):]

        try:
            if self._use_draft:
                await self._send_via_draft(draft_text)
            else:
                await self._send_via_edit(draft_text)
            self._last_send_time = time.time()
            self._last_sent_length = current_len
            self._error_count = 0  # reset on success
        except telegram.error.BadRequest as e:
            error_str = str(e)
            if any(err in error_str for err in _DRAFT_UNAVAILABLE_ERRORS):
                # Draft transport unavailable — fall back to edit
                logger.info(
                    "Draft transport unavailable, falling back to edit",
                    chat_id=self.chat_id,
                    error=error_str,
                )
                self._use_draft = False
                # Retry immediately with edit transport
                try:
                    await self._send_via_edit(draft_text)
                    self._last_send_time = time.time()
                    self._last_sent_length = current_len
                except Exception:
                    self._handle_error()
            elif "Message is not modified" in error_str:
                # Same content — not an error, just skip
                self._last_send_time = time.time()
            elif "Message to edit not found" in error_str:
                # Message was deleted — re-create
                self._edit_message_id = None
                try:
                    await self._send_via_edit(draft_text)
                    self._last_send_time = time.time()
                    self._last_sent_length = current_len
                except Exception:
                    self._handle_error()
            else:
                self._handle_error()
        except Exception:
            self._handle_error()

    def _handle_error(self) -> None:
        """Track errors and disable after too many."""
        self._error_count += 1
        if self._error_count >= self._max_errors:
            logger.debug(
                "Draft streamer disabled after repeated errors",
                chat_id=self.chat_id,
                error_count=self._error_count,
            )
            self._enabled = False

    async def _send_via_draft(self, text: str) -> None:
        """Send via sendMessageDraft (private chats)."""
        kwargs = {
            "chat_id": self.chat_id,
            "text": text,
            "draft_id": self.draft_id,
        }
        if self.message_thread_id is not None:
            kwargs["message_thread_id"] = self.message_thread_id
        logger.debug(
            "Sending draft",
            transport="draft",
            text_len=len(text),
            preview=text[:80],
        )
        await self.bot.send_message_draft(**kwargs)

    async def _send_via_edit(self, text: str) -> None:
        """Send via editMessageText (group chat fallback).

        Creates a message on first call, then edits it on subsequent calls.
        """
        if self._edit_message_id is None:
            # Send initial message
            kwargs = {
                "chat_id": self.chat_id,
                "text": text,
            }
            if self.message_thread_id is not None:
                kwargs["message_thread_id"] = self.message_thread_id
            msg = await self.bot.send_message(**kwargs)
            self._edit_message_id = msg.message_id
        else:
            await self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self._edit_message_id,
            )

    async def clear(self) -> None:
        """Clear the draft bubble by sending an empty draft.

        Call this before sending the final response message so the draft
        bubble disappears cleanly instead of overlapping with the real message.
        """
        if not self._enabled:
            return
        try:
            if self._use_draft:
                # Send empty draft to dismiss the typing bubble
                await self.bot.send_message_draft(
                    chat_id=self.chat_id,
                    text="",
                    draft_id=self.draft_id,
                )
            elif self._edit_message_id is not None:
                # For edit-based transport, delete the preview message
                try:
                    await self.bot.delete_message(
                        chat_id=self.chat_id,
                        message_id=self._edit_message_id,
                    )
                except Exception:
                    pass
                self._edit_message_id = None
        except Exception:
            pass
        self._enabled = False

    @property
    def edit_message_id(self) -> Optional[int]:
        """Return the message ID used by edit transport (for cleanup)."""
        return self._edit_message_id
