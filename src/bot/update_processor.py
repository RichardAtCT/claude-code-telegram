"""Selective-concurrency update processor for PTB.

Regular updates (messages, commands) process sequentially per conversation
topic. Priority callbacks (stop:*) bypass the queue and run immediately so they
can interrupt the currently-running handler.
"""

import asyncio
from typing import Any, Awaitable, Optional, Tuple

from telegram import Update
from telegram.ext._baseupdateprocessor import BaseUpdateProcessor


class StopAwareUpdateProcessor(BaseUpdateProcessor):
    """Update processor that lets priority callbacks bypass sequential processing.

    PTB calls ``process_update(update, coroutine)`` for every incoming update.
    The base class holds a semaphore (max 256) then calls our
    ``do_process_update()``.

    For priority callbacks (``stop:*``): we just ``await coroutine`` -- runs
    immediately.
    For everything else: we acquire the lock for that Telegram chat/topic, so
    one topic remains ordered without blocking unrelated topics.

    A stop callback arrives while a text handler holds the lock -> stop
    callback runs concurrently -> fires the ``asyncio.Event`` -> the watcher
    task inside ``execute_command()`` calls ``client.interrupt()`` -> Claude
    stops -> ``run_command()`` returns -> handler finishes -> lock released.
    """

    _PRIORITY_PREFIXES = ("stop:",)

    def __init__(self) -> None:
        # High limit so priority callbacks are never blocked by semaphore
        super().__init__(max_concurrent_updates=256)
        self._conversation_locks: dict[Tuple[str, int, Optional[int]], asyncio.Lock] = {}
        self._fallback_lock = asyncio.Lock()

    @classmethod
    def _is_priority_callback(cls, update: object) -> bool:
        """Return True if the update is a priority callback query."""
        if not isinstance(update, Update):
            return False
        cb = update.callback_query
        return (
            cb is not None
            and cb.data is not None
            and cb.data.startswith(cls._PRIORITY_PREFIXES)
        )

    @staticmethod
    def _message_thread_id(message: object, chat: Optional[object]) -> Optional[int]:
        """Extract a stable topic/thread id from a Telegram message object."""
        thread_id = getattr(message, "message_thread_id", None)
        if isinstance(thread_id, int) and thread_id > 0:
            return thread_id

        direct_topic = getattr(message, "direct_messages_topic", None)
        direct_topic_id = (
            getattr(direct_topic, "topic_id", None) if direct_topic else None
        )
        if isinstance(direct_topic_id, int) and direct_topic_id > 0:
            return direct_topic_id

        if chat is not None and getattr(chat, "is_forum", False):
            return 1
        return None

    @classmethod
    def _conversation_lock_key(
        cls, update: object
    ) -> Optional[Tuple[str, int, Optional[int]]]:
        """Return the lock key for an update, or None for the fallback lock."""
        if not isinstance(update, Update):
            return None

        callback_query = update.callback_query
        message = getattr(callback_query, "message", None) if callback_query else None
        if message is None:
            message = update.effective_message

        chat = getattr(message, "chat", None) if message is not None else None
        if chat is None:
            chat = update.effective_chat

        chat_id = getattr(chat, "id", None)
        if isinstance(chat_id, int):
            return ("chat", chat_id, cls._message_thread_id(message, chat))

        effective_user = update.effective_user
        user_id = getattr(effective_user, "id", None)
        if isinstance(user_id, int):
            return ("user", user_id, None)

        return None

    def _lock_for_update(self, update: object) -> asyncio.Lock:
        """Return the per-conversation lock for an update."""
        key = self._conversation_lock_key(update)
        if key is None:
            return self._fallback_lock
        return self._conversation_locks.setdefault(key, asyncio.Lock())

    async def do_process_update(
        self,
        update: object,
        coroutine: Awaitable[Any],
    ) -> None:
        """Process an update, applying sequential lock for non-priority updates."""
        if self._is_priority_callback(update):
            # Run immediately -- no sequential lock
            await coroutine
        else:
            async with self._lock_for_update(update):
                await coroutine

    async def initialize(self) -> None:
        """Initialize the processor (no-op)."""

    async def shutdown(self) -> None:
        """Shutdown the processor (no-op)."""
