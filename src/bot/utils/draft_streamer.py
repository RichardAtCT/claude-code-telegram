"""Stream partial responses to Telegram via sendMessageDraft."""

import time
from typing import List, Optional

import structlog
import telegram

from src.utils.constants import TELEGRAM_MAX_MESSAGE_LENGTH

logger = structlog.get_logger()

# Max tool lines shown in the draft header
_MAX_TOOL_LINES = 10


def generate_draft_id(chat_id: int) -> int:
    """Generate a non-zero positive draft ID for a chat.

    The same draft_id causes Telegram to animate text transitions instead of
    replacing the draft wholesale, giving a smooth streaming effect.
    """
    return hash(f"{chat_id}:{time.time_ns()}") & 0x7FFFFFFF | 1


class DraftStreamer:
    """Accumulates streamed text and sends periodic drafts to Telegram.

    The draft is composed of two sections:

    1. **Tool header** — compact lines showing tool calls and reasoning
       snippets as they arrive, e.g. ``"📖 Read  |  🔍 Grep  |  🐚 Bash"``.
    2. **Response body** — the actual assistant response text, streamed
       token-by-token.

    Both sections are combined into a single draft message and sent via
    ``sendMessageDraft``.

    Key design decisions:
    - Plain text drafts (no parse_mode) to avoid partial HTML/markdown errors.
    - Tail-truncation for messages >4096 chars: shows ``"\\u2026" + last 4093 chars``.
    - Self-disabling: any API error silently disables the streamer so the
      request continues with normal (non-streaming) delivery.
    """

    def __init__(
        self,
        bot: telegram.Bot,
        chat_id: int,
        draft_id: int,
        message_thread_id: Optional[int] = None,
        throttle_interval: float = 0.3,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.draft_id = draft_id
        self.message_thread_id = message_thread_id
        self.throttle_interval = throttle_interval

        self._tool_lines: List[str] = []
        self._accumulated_text = ""
        self._last_send_time = 0.0
        self._enabled = True

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
        await self._send_draft()

    def _compose_draft(self) -> str:
        """Combine tool header and response body into a single draft."""
        parts: List[str] = []

        if self._tool_lines:
            visible = self._tool_lines[-_MAX_TOOL_LINES:]
            if len(self._tool_lines) > _MAX_TOOL_LINES:
                parts.append(
                    f"... +{len(self._tool_lines) - _MAX_TOOL_LINES} more"
                )
            parts.extend(visible)

        if self._accumulated_text:
            if parts:
                parts.append("")  # blank separator line
            parts.append(self._accumulated_text)

        return "\n".join(parts)

    async def _send_draft(self) -> None:
        """Send the composed draft (tools + text) as a message draft."""
        draft_text = self._compose_draft()
        if not draft_text.strip():
            return

        # Tail-truncate if over Telegram limit
        if len(draft_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            draft_text = "\u2026" + draft_text[-(TELEGRAM_MAX_MESSAGE_LENGTH - 1) :]

        try:
            kwargs = {
                "chat_id": self.chat_id,
                "text": draft_text,
                "draft_id": self.draft_id,
            }
            if self.message_thread_id is not None:
                kwargs["message_thread_id"] = self.message_thread_id
            await self.bot.send_message_draft(**kwargs)
            self._last_send_time = time.time()
        except Exception:
            logger.debug(
                "Draft send failed, disabling streamer",
                chat_id=self.chat_id,
            )
            self._enabled = False
