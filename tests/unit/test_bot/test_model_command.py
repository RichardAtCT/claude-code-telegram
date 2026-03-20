"""Tests for the /model command — runtime model and effort switching.

Covers:
- /model shows inline keyboard with model choices
- Model selection sets model_override and force_new_session
- Effort selection sets effort_override
- "default" clears all overrides
- Haiku skips effort keyboard (not supported)
- Opus shows "max" effort, Sonnet does not
- _current_model_label returns correct labels
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardMarkup

from src.bot.handlers.command import (
    _EFFORT_BY_MODEL,
    _MODELS,
    _current_model_label,
    _handle_model_selection,
    model_command,
)
from src.config.settings import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path):
    return Settings(
        telegram_bot_token="test:token",
        telegram_bot_username="testbot",
        approved_directory=tmp_path,
    )


@pytest.fixture
def context(settings):
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.bot_data = {"settings": settings}
    ctx.args = None
    return ctx


@pytest.fixture
def update(context):
    upd = MagicMock()
    upd.message = AsyncMock()
    upd.effective_user.id = 12345
    return upd


@pytest.fixture
def callback_query():
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 12345
    return query


# ---------------------------------------------------------------------------
# /model command (keyboard display)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_command_shows_keyboard(update, context):
    """Verify /model sends an inline keyboard with model choices."""
    await model_command(update, context)

    update.message.reply_text.assert_called_once()
    call_kwargs = update.message.reply_text.call_args
    assert isinstance(call_kwargs.kwargs["reply_markup"], InlineKeyboardMarkup)
    # Should contain the session warning
    assert "new session" in call_kwargs.args[0].lower()


@pytest.mark.asyncio
async def test_model_command_shows_current_override(update, context):
    """When an override is active, /model should show it."""
    context.user_data["model_override"] = _MODELS["sonnet"]
    await model_command(update, context)

    text = update.message.reply_text.call_args.args[0]
    assert "Sonnet" in text


# ---------------------------------------------------------------------------
# Model selection callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_opus_sets_override(callback_query, context):
    """Selecting Opus sets model_override and force_new_session."""
    await _handle_model_selection(callback_query, "model:opus", context)

    assert context.user_data["model_override"] == _MODELS["opus"]
    assert context.user_data["force_new_session"] is True


@pytest.mark.asyncio
async def test_select_sonnet_sets_override(callback_query, context):
    """Selecting Sonnet sets the correct model ID."""
    await _handle_model_selection(callback_query, "model:sonnet", context)

    assert context.user_data["model_override"] == _MODELS["sonnet"]


@pytest.mark.asyncio
async def test_select_haiku_skips_effort(callback_query, context):
    """Selecting Haiku should not show effort keyboard (not supported)."""
    await _handle_model_selection(callback_query, "model:haiku", context)

    assert context.user_data["model_override"] == _MODELS["haiku"]
    # Final message, no reply_markup (no effort keyboard)
    call_kwargs = callback_query.edit_message_text.call_args
    assert "reply_markup" not in call_kwargs.kwargs or call_kwargs.kwargs.get("reply_markup") is None
    assert "ready" in call_kwargs.args[0].lower()


@pytest.mark.asyncio
async def test_select_opus_shows_effort_with_max(callback_query, context):
    """Opus should show effort keyboard including 'max'."""
    await _handle_model_selection(callback_query, "model:opus", context)

    call_kwargs = callback_query.edit_message_text.call_args
    markup = call_kwargs.kwargs.get("reply_markup")
    assert markup is not None
    # Flatten button labels
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "Max" in labels
    assert "effort" in call_kwargs.args[0].lower()


@pytest.mark.asyncio
async def test_select_sonnet_shows_effort_without_max(callback_query, context):
    """Sonnet should show effort keyboard without 'max'."""
    await _handle_model_selection(callback_query, "model:sonnet", context)

    call_kwargs = callback_query.edit_message_text.call_args
    markup = call_kwargs.kwargs.get("reply_markup")
    assert markup is not None
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "Max" not in labels
    assert "High" in labels


@pytest.mark.asyncio
async def test_default_clears_overrides(callback_query, context):
    """Selecting 'default' clears model, effort, and forces new session."""
    context.user_data["model_override"] = _MODELS["opus"]
    context.user_data["effort_override"] = "high"

    await _handle_model_selection(callback_query, "model:default", context)

    assert "model_override" not in context.user_data
    assert "effort_override" not in context.user_data
    assert context.user_data["force_new_session"] is True


# ---------------------------------------------------------------------------
# Effort selection callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_effort_sets_override(callback_query, context):
    """Selecting an effort level stores it in user_data."""
    context.user_data["model_override"] = _MODELS["opus"]

    await _handle_model_selection(callback_query, "effort:high", context)

    assert context.user_data["effort_override"] == "high"


@pytest.mark.asyncio
async def test_effort_skip_keeps_existing(callback_query, context):
    """Selecting 'skip' should not set effort_override."""
    context.user_data["model_override"] = _MODELS["sonnet"]

    await _handle_model_selection(callback_query, "effort:skip", context)

    assert "effort_override" not in context.user_data


@pytest.mark.asyncio
async def test_model_switch_clears_stale_effort(callback_query, context):
    """Switching models should clear any previous effort override."""
    context.user_data["effort_override"] = "high"

    await _handle_model_selection(callback_query, "model:haiku", context)

    assert "effort_override" not in context.user_data


# ---------------------------------------------------------------------------
# Label helper
# ---------------------------------------------------------------------------


def test_label_default():
    ctx = MagicMock()
    ctx.user_data = {}
    assert _current_model_label(ctx) == "Default"


def test_label_with_model_and_effort():
    ctx = MagicMock()
    ctx.user_data = {"model_override": _MODELS["sonnet"], "effort_override": "medium"}
    assert _current_model_label(ctx) == "Sonnet | effort=medium"


def test_label_model_only():
    ctx = MagicMock()
    ctx.user_data = {"model_override": _MODELS["opus"]}
    assert _current_model_label(ctx) == "Opus"


# ---------------------------------------------------------------------------
# Effort level configuration
# ---------------------------------------------------------------------------


def test_haiku_has_no_effort_levels():
    assert _EFFORT_BY_MODEL["haiku"] == []


def test_sonnet_has_no_max():
    assert "max" not in _EFFORT_BY_MODEL["sonnet"]
    assert "high" in _EFFORT_BY_MODEL["sonnet"]


def test_opus_has_max():
    assert "max" in _EFFORT_BY_MODEL["opus"]
