"""Tests for StopAwareUpdateProcessor.

Covers:
- Stop callbacks bypass topic locks (run immediately)
- Regular updates are serialized within one conversation topic
- Regular updates in different topics can overlap
- Non-stop callbacks (e.g. cd:) go through the topic lock
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from telegram import CallbackQuery, Update

from src.bot.update_processor import StopAwareUpdateProcessor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_update(
    callback_data: str | None = None,
    *,
    chat_id: int = 123,
    message_thread_id: int | None = None,
    callback_message_thread_id: int | None = None,
) -> Update:
    """Build a minimal Update mock with optional callback_query data."""
    update = MagicMock(spec=Update)
    chat = SimpleNamespace(id=chat_id)
    if callback_data is not None:
        cb = MagicMock(spec=CallbackQuery)
        cb.data = callback_data
        cb.message = SimpleNamespace(
            chat=chat,
            message_thread_id=(
                callback_message_thread_id
                if callback_message_thread_id is not None
                else message_thread_id
            ),
        )
        update.callback_query = cb
        update.effective_chat = chat
        update.effective_message = cb.message
    else:
        message = SimpleNamespace(chat=chat, message_thread_id=message_thread_id)
        update.callback_query = None
        update.effective_chat = chat
        update.effective_message = message
    return update


# ---------------------------------------------------------------------------
# _is_priority_callback
# ---------------------------------------------------------------------------


class TestIsPriorityCallback:
    def test_stop_callback_detected(self):
        update = _make_update("stop:123")
        assert StopAwareUpdateProcessor._is_priority_callback(update) is True

    def test_cd_callback_not_priority(self):
        update = _make_update("cd:my_project")
        assert StopAwareUpdateProcessor._is_priority_callback(update) is False

    def test_no_callback_query(self):
        update = _make_update(None)
        assert StopAwareUpdateProcessor._is_priority_callback(update) is False

    def test_non_update_object(self):
        assert StopAwareUpdateProcessor._is_priority_callback("not an update") is False

    def test_callback_with_none_data(self):
        update = MagicMock(spec=Update)
        cb = MagicMock(spec=CallbackQuery)
        cb.data = None
        update.callback_query = cb
        assert StopAwareUpdateProcessor._is_priority_callback(update) is False


# ---------------------------------------------------------------------------
# do_process_update — concurrency tests
# ---------------------------------------------------------------------------


class TestStopCallbackBypassesLock:
    async def test_stop_callback_runs_while_lock_held(self):
        """A stop callback runs immediately even when a topic lock is held."""
        processor = StopAwareUpdateProcessor()

        execution_order: list[str] = []
        lock_acquired = asyncio.Event()
        stop_done = asyncio.Event()

        async def slow_coroutine():
            execution_order.append("regular_start")
            lock_acquired.set()
            await stop_done.wait()
            execution_order.append("regular_end")

        async def stop_coroutine():
            execution_order.append("stop_start")
            execution_order.append("stop_end")
            stop_done.set()

        regular_update = _make_update(None, chat_id=123, message_thread_id=10)
        stop_update = _make_update("stop:42", chat_id=123, message_thread_id=10)

        regular_task = asyncio.create_task(
            processor.do_process_update(regular_update, slow_coroutine())
        )
        await lock_acquired.wait()

        stop_task = asyncio.create_task(
            processor.do_process_update(stop_update, stop_coroutine())
        )

        await asyncio.gather(regular_task, stop_task)

        assert execution_order == [
            "regular_start",
            "stop_start",
            "stop_end",
            "regular_end",
        ]


class TestRegularUpdatesSequential:
    async def test_two_regular_updates_in_same_topic_do_not_overlap(self):
        """Two regular updates in the same topic are serialized."""
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

        update_a = _make_update(None, chat_id=123, message_thread_id=10)
        update_b = _make_update(None, chat_id=123, message_thread_id=10)

        task_a = asyncio.create_task(
            processor.do_process_update(update_a, coroutine_a())
        )
        await asyncio.sleep(0)

        task_b = asyncio.create_task(
            processor.do_process_update(update_b, coroutine_b())
        )

        await asyncio.gather(task_a, task_b)

        assert execution_log == ["a_start", "a_end", "b_start", "b_end"]

    async def test_two_regular_updates_in_different_topics_can_overlap(self):
        """Different Telegram forum topics should not share a global queue."""
        processor = StopAwareUpdateProcessor()

        execution_log: list[str] = []
        a_started = asyncio.Event()
        b_started = asyncio.Event()
        release = asyncio.Event()

        async def coroutine_a():
            execution_log.append("a_start")
            a_started.set()
            await b_started.wait()
            await release.wait()
            execution_log.append("a_end")

        async def coroutine_b():
            await a_started.wait()
            execution_log.append("b_start")
            b_started.set()
            await release.wait()
            execution_log.append("b_end")

        update_a = _make_update(None, chat_id=-100, message_thread_id=10)
        update_b = _make_update(None, chat_id=-100, message_thread_id=20)

        task_a = asyncio.create_task(
            processor.do_process_update(update_a, coroutine_a())
        )
        await a_started.wait()
        task_b = asyncio.create_task(
            processor.do_process_update(update_b, coroutine_b())
        )

        await asyncio.wait_for(b_started.wait(), timeout=0.2)
        release.set()
        await asyncio.gather(task_a, task_b)

        assert execution_log[:2] == ["a_start", "b_start"]


class TestNonStopCallbackSequential:
    async def test_cd_callback_waits_for_same_topic_lock(self):
        """Non-stop callbacks (cd:*) are serialized with their topic."""
        processor = StopAwareUpdateProcessor()

        execution_log: list[str] = []

        async def regular_coroutine():
            execution_log.append("regular_start")
            await asyncio.sleep(0.05)
            execution_log.append("regular_end")

        async def cd_coroutine():
            execution_log.append("cd_start")
            execution_log.append("cd_end")

        regular_update = _make_update(None, chat_id=123, message_thread_id=10)
        cd_update = _make_update(
            "cd:my_project", chat_id=123, callback_message_thread_id=10
        )

        task_regular = asyncio.create_task(
            processor.do_process_update(regular_update, regular_coroutine())
        )
        await asyncio.sleep(0)

        task_cd = asyncio.create_task(
            processor.do_process_update(cd_update, cd_coroutine())
        )

        await asyncio.gather(task_regular, task_cd)

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
