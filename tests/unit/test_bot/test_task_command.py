"""Tests for /task command."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.handlers.command import task_command
from src.storage.models import TaskModel


def make_update_ctx(user_id: int, args: list):
    user = MagicMock()
    user.id = user_id
    message = MagicMock()
    message.reply_text = AsyncMock()
    update = MagicMock()
    update.effective_user = user
    update.message = message
    context = MagicMock()
    context.args = args
    storage = MagicMock()
    context.bot_data = {"storage": storage}
    return update, context, storage


async def test_task_add_creates_task():
    update, context, storage = make_update_ctx(1, ["add", "Buy", "milk"])
    storage.tasks.create_task = AsyncMock(
        return_value=TaskModel(id=1, user_id=1, title="Buy milk")
    )

    await task_command(update, context)

    storage.tasks.create_task.assert_awaited_once()
    call_arg = storage.tasks.create_task.call_args[0][0]
    assert call_arg.title == "Buy milk"


async def test_task_list_shows_open_tasks():
    update, context, storage = make_update_ctx(1, ["list"])
    storage.tasks.list_tasks = AsyncMock(return_value=[
        TaskModel(id=1, user_id=1, title="Buy milk", status="open"),
        TaskModel(id=2, user_id=1, title="Call doctor", status="open"),
    ])

    await task_command(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert "Buy milk" in text
    assert "Call doctor" in text


async def test_task_list_empty():
    update, context, storage = make_update_ctx(1, ["list"])
    storage.tasks.list_tasks = AsyncMock(return_value=[])

    await task_command(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert "no" in text.lower() or "empty" in text.lower()


async def test_task_done_marks_complete():
    update, context, storage = make_update_ctx(1, ["done", "3"])
    storage.tasks.update_task_status = AsyncMock(return_value=True)

    await task_command(update, context)

    storage.tasks.update_task_status.assert_awaited_once_with(3, "done")


async def test_task_no_args_shows_help():
    update, context, storage = make_update_ctx(1, [])

    await task_command(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "add" in text.lower()
