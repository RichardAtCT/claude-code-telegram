"""Tests for StopAwareUpdateProcessor.

Covers:
- Stop callbacks bypass the sequential lock (run immediately)
- Regular updates are serialized (only one at a time)
- Non-stop callbacks (e.g. cd:) go through the sequential lock
"""

import asyncio
from unittest.mock import MagicMock

from telegram import CallbackQuery, Update

from src.bot.update_processor import StopAwareUpdateProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_update(callback_data: str | None = None) -> Update:
    """Build a minimal Update mock with optional callback_query data."""
    update = MagicMock(spec=Update)
    if callback_data is not None:
        cb = MagicMock(spec=CallbackQuery)
        cb.data = callback_data
        update.callback_query = cb
    else:
        update.callback_query = None
    return update


# ---------------------------------------------------------------------------
# _is_stop_callback
# ---------------------------------------------------------------------------


class TestIsStopCallback:
    def test_stop_callback_detected(self):
        update = _make_update("stop:123")
        assert StopAwareUpdateProcessor._is_stop_callback(update) is True

    def test_cd_callback_not_stop(self):
        update = _make_update("cd:my_project")
        assert StopAwareUpdateProcessor._is_stop_callback(update) is False

    def test_no_callback_query(self):
        update = _make_update(None)
        assert StopAwareUpdateProcessor._is_stop_callback(update) is False

    def test_non_update_object(self):
        assert StopAwareUpdateProcessor._is_stop_callback("not an update") is False

    def test_callback_with_none_data(self):
        update = MagicMock(spec=Update)
        cb = MagicMock(spec=CallbackQuery)
        cb.data = None
        update.callback_query = cb
        assert StopAwareUpdateProcessor._is_stop_callback(update) is False


# ---------------------------------------------------------------------------
# do_process_update — concurrency tests
# ---------------------------------------------------------------------------


class TestStopCallbackBypassesLock:
    async def test_stop_callback_runs_while_lock_held(self):
        """A stop callback runs immediately even when sequential lock is held."""
        processor = StopAwareUpdateProcessor()

        execution_order: list[str] = []
        lock_acquired = asyncio.Event()
        stop_done = asyncio.Event()

        async def slow_coroutine():
            execution_order.append("regular_start")
            lock_acquired.set()
            # Wait for the stop callback to finish
            await stop_done.wait()
            execution_order.append("regular_end")

        async def stop_coroutine():
            execution_order.append("stop_start")
            execution_order.append("stop_end")
            stop_done.set()

        regular_update = _make_update(None)
        stop_update = _make_update("stop:42")

        # Start the regular update (acquires lock)
        regular_task = asyncio.create_task(
            processor.do_process_update(regular_update, slow_coroutine())
        )

        # Wait for the regular update to hold the lock
        await lock_acquired.wait()

        # Now fire the stop callback — should run immediately
        stop_task = asyncio.create_task(
            processor.do_process_update(stop_update, stop_coroutine())
        )

        await asyncio.gather(regular_task, stop_task)

        # Stop ran WHILE regular was still in progress
        assert execution_order == [
            "regular_start",
            "stop_start",
            "stop_end",
            "regular_end",
        ]


class TestRegularUpdatesSequential:
    async def test_two_regular_updates_do_not_overlap(self):
        """Two regular updates are serialized by the sequential lock."""
        processor = StopAwareUpdateProcessor()

        execution_log: list[str] = []

        async def coroutine_a():
            execution_log.append("a_start")
            await asyncio.sleep(0.05)
            execution_log.append("a_end")

        async def coroutine_b():
            execution_log.append("b_start")
            await asyncio.sleep(0.05)
            execution_log.append("b_end")

        update_a = _make_update(None)
        update_b = _make_update(None)

        task_a = asyncio.create_task(
            processor.do_process_update(update_a, coroutine_a())
        )
        # Yield so task_a starts and acquires the lock
        await asyncio.sleep(0)

        task_b = asyncio.create_task(
            processor.do_process_update(update_b, coroutine_b())
        )

        await asyncio.gather(task_a, task_b)

        # b should not start until a has finished
        assert execution_log == ["a_start", "a_end", "b_start", "b_end"]


class TestNonStopCallbackSequential:
    async def test_cd_callback_goes_through_sequential_lock(self):
        """Non-stop callbacks (cd:*) are treated as regular updates."""
        processor = StopAwareUpdateProcessor()

        execution_log: list[str] = []

        async def regular_coroutine():
            execution_log.append("regular_start")
            await asyncio.sleep(0.05)
            execution_log.append("regular_end")

        async def cd_coroutine():
            execution_log.append("cd_start")
            execution_log.append("cd_end")

        regular_update = _make_update(None)
        cd_update = _make_update("cd:my_project")

        task_regular = asyncio.create_task(
            processor.do_process_update(regular_update, regular_coroutine())
        )
        await asyncio.sleep(0)

        task_cd = asyncio.create_task(
            processor.do_process_update(cd_update, cd_coroutine())
        )

        await asyncio.gather(task_regular, task_cd)

        # cd callback waited for regular to finish
        assert execution_log == [
            "regular_start",
            "regular_end",
            "cd_start",
            "cd_end",
        ]


class TestInitializeShutdown:
    async def test_initialize_and_shutdown_are_noop(self):
        """initialize() and shutdown() should not raise."""
        processor = StopAwareUpdateProcessor()
        await processor.initialize()
        await processor.shutdown()
