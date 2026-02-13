"""Notification service for delivering proactive agent responses to Telegram.

Subscribes to AgentResponseEvent on the event bus and delivers messages
through the Telegram bot API with rate limiting (1 msg/sec per chat).
"""

import asyncio
from typing import List, Optional

import structlog
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from ..events.bus import Event, EventBus
from ..events.types import AgentResponseEvent

logger = structlog.get_logger()

# Telegram rate limit: ~30 msgs/sec globally, ~1 msg/sec per chat
SEND_INTERVAL_SECONDS = 1.1


class NotificationService:
    """Delivers agent responses to Telegram chats with rate limiting."""

    def __init__(
        self,
        event_bus: EventBus,
        bot: Bot,
        default_chat_ids: Optional[List[int]] = None,
    ) -> None:
        self.event_bus = event_bus
        self.bot = bot
        self.default_chat_ids = default_chat_ids or []
        self._send_queue: asyncio.Queue[AgentResponseEvent] = asyncio.Queue()
        self._last_send_per_chat: dict[int, float] = {}
        self._running = False
        self._sender_task: Optional[asyncio.Task[None]] = None

    def register(self) -> None:
        """Subscribe to agent response events."""
        self.event_bus.subscribe(AgentResponseEvent, self.handle_response)

    async def start(self) -> None:
        """Start the send queue processor."""
        if self._running:
            return
        self._running = True
        self._sender_task = asyncio.create_task(self._process_send_queue())
        logger.info("Notification service started")

    async def stop(self) -> None:
        """Stop the send queue processor."""
        if not self._running:
            return
        self._running = False
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
        logger.info("Notification service stopped")

    async def handle_response(self, event: Event) -> None:
        """Queue an agent response for delivery."""
        if not isinstance(event, AgentResponseEvent):
            return
        await self._send_queue.put(event)

    async def _process_send_queue(self) -> None:
        """Process queued messages with rate limiting."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            chat_ids = self._resolve_chat_ids(event)
            for chat_id in chat_ids:
                await self._rate_limited_send(chat_id, event)

    def _resolve_chat_ids(self, event: AgentResponseEvent) -> List[int]:
        """Determine which chats to send to."""
        if event.chat_id and event.chat_id != 0:
            return [event.chat_id]
        return list(self.default_chat_ids)

    async def _rate_limited_send(self, chat_id: int, event: AgentResponseEvent) -> None:
        """Send message with per-chat rate limiting."""
        loop = asyncio.get_event_loop()
        now = loop.time()
        last_send = self._last_send_per_chat.get(chat_id, 0.0)
        wait_time = SEND_INTERVAL_SECONDS - (now - last_send)

        if wait_time > 0:
            await asyncio.sleep(wait_time)

        try:
            # Split long messages (Telegram limit: 4096 chars)
            text = event.text
            chunks = self._split_message(text)

            for chunk in chunks:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=(ParseMode.HTML if event.parse_mode == "HTML" else None),
                )
                self._last_send_per_chat[chat_id] = asyncio.get_event_loop().time()

                # Rate limit between chunks too
                if len(chunks) > 1:
                    await asyncio.sleep(SEND_INTERVAL_SECONDS)

            logger.info(
                "Notification sent",
                chat_id=chat_id,
                text_length=len(text),
                chunks=len(chunks),
                originating_event=event.originating_event_id,
            )
        except TelegramError as e:
            logger.error(
                "Failed to send notification",
                chat_id=chat_id,
                error=str(e),
                event_id=event.id,
            )

    def _split_message(self, text: str, max_length: int = 4096) -> List[str]:
        """Split long messages at paragraph boundaries."""
        if len(text) <= max_length:
            return [text]

        chunks: List[str] = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break

            # Try to split at a paragraph boundary
            split_pos = text.rfind("\n\n", 0, max_length)
            if split_pos == -1:
                # Try single newline
                split_pos = text.rfind("\n", 0, max_length)
            if split_pos == -1:
                # Try space
                split_pos = text.rfind(" ", 0, max_length)
            if split_pos == -1:
                # Hard split
                split_pos = max_length

            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()

        return chunks
