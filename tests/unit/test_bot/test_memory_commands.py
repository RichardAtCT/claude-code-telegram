"""Tests for /remember, /forget, /memories commands."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update

from src.bot.handlers.command import forget_command, memories_command, remember_command
from src.storage.models import UserMemoryModel


def make_update(user_id: int, args: list) -> tuple:
    user = MagicMock()
    user.id = user_id
    message = MagicMock()
    message.reply_text = AsyncMock()
    message.from_user = user
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message
    context = MagicMock()
    context.args = args
    context.bot_data = {}
    return update, context


async def test_remember_saves_memory():
    update, context = make_update(1, ["hobby:", "orienteering"])
    storage = MagicMock()
    storage.memories.set_memory = AsyncMock()
    context.bot_data["storage"] = storage

    await remember_command(update, context)

    storage.memories.set_memory.assert_awaited_once()
    update.message.reply_text.assert_awaited_once()


async def test_remember_requires_args():
    update, context = make_update(1, [])
    storage = MagicMock()
    context.bot_data["storage"] = storage

    await remember_command(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "usage" in text.lower() or "provide" in text.lower()


async def test_memories_lists_memories():
    update, context = make_update(1, [])
    storage = MagicMock()
    storage.memories.list_memories = AsyncMock(return_value=[
        UserMemoryModel(id=1, user_id=1, key="hobby", value="running"),
        UserMemoryModel(id=2, user_id=1, key="city", value="Vilnius"),
    ])
    context.bot_data["storage"] = storage

    await memories_command(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert "hobby" in text
    assert "running" in text


async def test_forget_deletes_memory():
    update, context = make_update(1, ["1"])
    storage = MagicMock()
    storage.memories.delete_memory = AsyncMock(return_value=True)
    context.bot_data["storage"] = storage

    await forget_command(update, context)

    storage.memories.delete_memory.assert_awaited_once_with(1, 1)
    text = update.message.reply_text.call_args[0][0]
    assert "deleted" in text.lower() or "✅" in text
