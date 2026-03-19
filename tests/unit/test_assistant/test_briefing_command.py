"""Tests for /briefing command."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.handlers.command import briefing_command
from src.storage.models import UserProfileModel


def make_ctx(user_id: int, args: list, profile=None):
    user = MagicMock()
    user.id = user_id
    message = MagicMock()
    message.reply_text = AsyncMock()
    message.chat_id = user_id
    update = MagicMock()
    update.effective_user = user
    update.message = message
    storage = MagicMock()
    storage.profiles.get_profile = AsyncMock(return_value=profile)
    storage.profiles.upsert_profile = AsyncMock()
    storage.memories.list_memories = AsyncMock(return_value=[])
    storage.tasks.list_tasks = AsyncMock(return_value=[])
    assembler = MagicMock()
    assembler.build = AsyncMock(return_value="Good morning!")
    context = MagicMock()
    context.args = args
    context.bot_data = {"storage": storage, "briefing_assembler": assembler}
    return update, context, storage, assembler


async def test_briefing_now_sends_briefing():
    update, context, storage, assembler = make_ctx(1, ["now"])

    await briefing_command(update, context)

    assembler.build.assert_awaited_once_with(user_id=1)
    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Good morning!" in text


async def test_briefing_off_disables_briefing():
    profile = UserProfileModel(user_id=1, briefing_enabled=True, briefing_cron="0 8 * * *")
    update, context, storage, assembler = make_ctx(1, ["off"], profile=profile)

    await briefing_command(update, context)

    storage.profiles.upsert_profile.assert_awaited_once()
    saved = storage.profiles.upsert_profile.call_args[0][0]
    assert saved.briefing_enabled is False


async def test_briefing_no_args_shows_status():
    profile = UserProfileModel(user_id=1, briefing_enabled=True, briefing_cron="0 9 * * *")
    update, context, storage, assembler = make_ctx(1, [], profile=profile)

    await briefing_command(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert "briefing" in text.lower()
