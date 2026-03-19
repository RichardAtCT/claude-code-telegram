"""Tests for /profile command handler."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, Update, User

from src.bot.handlers.command import profile_command
from src.storage.models import UserProfileModel


def make_update(user_id: int, text: str) -> Update:
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = "testuser"
    message = MagicMock(spec=Message)
    message.text = text
    message.reply_text = AsyncMock()
    message.from_user = user
    chat = MagicMock(spec=Chat)
    chat.id = user_id
    message.chat = chat
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message
    return update


async def test_profile_shows_empty_profile():
    update = make_update(1, "/profile")
    storage = MagicMock()
    storage.profiles.get_profile = AsyncMock(return_value=None)
    context = MagicMock()
    context.bot_data = {"storage": storage}
    context.args = []

    await profile_command(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "profile" in text.lower() or "not set" in text.lower()


async def test_profile_shows_existing_profile():
    update = make_update(1, "/profile")
    profile = UserProfileModel(user_id=1, name="Paulius", timezone="Europe/Vilnius")
    storage = MagicMock()
    storage.profiles.get_profile = AsyncMock(return_value=profile)
    context = MagicMock()
    context.bot_data = {"storage": storage}
    context.args = []

    await profile_command(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert "Paulius" in text
    assert "Europe/Vilnius" in text
