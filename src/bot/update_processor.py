"""Selective-concurrency update processor for PTB.

Regular updates (messages, commands) process sequentially -- one at a time.
Stop button callbacks (stop:*) bypass the queue and run immediately so they
can interrupt the currently-running handler via asyncio.Event.
"""

import asyncio
from typing import Any, Awaitable

from telegram import Update
from telegram.ext._baseupdateprocessor import BaseUpdateProcessor


class StopAwareUpdateProcessor(BaseUpdateProcessor):
    """Update processor that lets stop callbacks bypass sequential processing.

    PTB calls ``process_update(update, coroutine)`` for every incoming update.
    The base class holds a semaphore (max 256) then calls our
    ``do_process_update()``.

    For ``stop:*`` callbacks: we just ``await coroutine`` -- runs immediately.
    For everything else: we acquire ``_sequential_lock`` first -- only one
    runs at a time.

    A stop callback arrives while a text handler holds the lock -> stop
    callback runs concurrently -> fires the ``asyncio.Event`` -> the watcher
    task inside ``execute_command()`` calls ``client.interrupt()`` -> Claude
    stops -> ``run_command()`` returns -> handler finishes -> lock released.
    """

    _MAX_CONCURRENT = 256  # High enough to never block stop callbacks

    def __init__(self) -> None:
        super().__init__(max_concurrent_updates=self._MAX_CONCURRENT)
        self._sequential_lock = asyncio.Lock()

    @staticmethod
    def _is_stop_callback(update: object) -> bool:
        """Return True if the update is a stop button callback query."""
        if not isinstance(update, Update):
            return False
        cb = update.callback_query
        return cb is not None and cb.data is not None and cb.data.startswith("stop:")

    async def do_process_update(
        self,
        update: object,
        coroutine: Awaitable[Any],
    ) -> None:
        """Process an update, applying sequential lock for non-stop updates."""
        if self._is_stop_callback(update):
            # Run immediately -- no sequential lock
            await coroutine
        else:
            # One at a time for everything else
            async with self._sequential_lock:
                await coroutine

    async def initialize(self) -> None:
        """Initialize the processor (no-op)."""

    async def shutdown(self) -> None:
        """Shutdown the processor (no-op)."""
