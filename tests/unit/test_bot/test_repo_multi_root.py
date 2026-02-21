"""Tests for /repo multi-root directory support in the agentic orchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import create_test_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dual_root_settings(tmp_path: Path):
    """Two approved roots, each with one sub-directory (repo)."""
    root1 = tmp_path / "work"
    root2 = tmp_path / "personal"
    root1.mkdir()
    root2.mkdir()
    (root1 / "project_a").mkdir()
    (root2 / "blog").mkdir()

    settings = create_test_config(
        approved_directory=str(root1),
        approved_directories_str=f"{root1},{root2}",
    )
    return settings, root1, root2


# ---------------------------------------------------------------------------
# Orchestrator._agentic_callback (cd: callback)
# ---------------------------------------------------------------------------


async def test_agentic_callback_valid_root_name(dual_root_settings, tmp_path: Path):
    """cd callback with a valid root name routes to the correct directory."""
    from src.bot.orchestrator import MessageOrchestrator

    settings, root1, root2 = dual_root_settings

    orchestrator = MagicMock(spec=MessageOrchestrator)
    orchestrator.settings = settings
    orchestrator._agentic_callback = MessageOrchestrator._agentic_callback.__get__(
        orchestrator
    )

    query = AsyncMock()
    query.data = f"cd:{root2.name}:blog"
    query.edit_message_text = AsyncMock()
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = 1

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"claude_integration": None}

    await orchestrator._agentic_callback(update, context)

    # Directory was updated to the correct path
    assert context.user_data.get("current_directory") == (root2 / "blog").resolve()
    # The success confirmation was sent (not an error)
    query.edit_message_text.assert_called_once()
    confirmation_text = query.edit_message_text.call_args[0][0]
    assert "blog" in confirmation_text
    assert "not found" not in confirmation_text.lower()


async def test_agentic_callback_unknown_root_name(dual_root_settings):
    """cd callback with an unknown root name shows an error and does not navigate."""
    from src.bot.orchestrator import MessageOrchestrator

    settings, root1, root2 = dual_root_settings

    orchestrator = MagicMock(spec=MessageOrchestrator)
    orchestrator.settings = settings
    orchestrator._agentic_callback = MessageOrchestrator._agentic_callback.__get__(
        orchestrator
    )

    query = AsyncMock()
    query.data = "cd:nonexistent_root:project_a"
    query.edit_message_text = AsyncMock()
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = 1

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {}

    await orchestrator._agentic_callback(update, context)

    query.edit_message_text.assert_called_once()
    call_text = query.edit_message_text.call_args[0][0]
    assert "not found" in call_text.lower() or "run /repo" in call_text.lower()
    # Directory must NOT have been changed
    assert "current_directory" not in context.user_data


async def testagentic_repo_listing_aggregates_all_roots(
    dual_root_settings, tmp_path: Path
):
    """agentic_repo lists repos from every approved root."""
    from src.bot.orchestrator import MessageOrchestrator

    settings, root1, root2 = dual_root_settings

    orchestrator = MagicMock(spec=MessageOrchestrator)
    orchestrator.settings = settings
    orchestrator.agentic_repo = MessageOrchestrator.agentic_repo.__get__(orchestrator)

    message = AsyncMock()
    message.text = "/repo"
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.message = message
    update.effective_user.id = 1

    context = MagicMock()
    context.user_data = {"current_directory": root1}
    context.bot_data = {}

    await orchestrator.agentic_repo(update, context)

    message.reply_text.assert_called_once()
    reply_text = message.reply_text.call_args[0][0]
    # Both repos should appear in the listing
    assert "project_a" in reply_text
    assert "blog" in reply_text


async def testagentic_repo_callback_encodes_root_name(
    dual_root_settings, tmp_path: Path
):
    """Inline keyboard buttons encode root *name*, not positional index."""
    from src.bot.orchestrator import MessageOrchestrator

    settings, root1, root2 = dual_root_settings

    orchestrator = MagicMock(spec=MessageOrchestrator)
    orchestrator.settings = settings
    orchestrator.agentic_repo = MessageOrchestrator.agentic_repo.__get__(orchestrator)

    message = AsyncMock()
    message.text = "/repo"
    reply_markup_holder: list = []

    async def capture_reply(text, **kwargs):
        reply_markup_holder.append(kwargs.get("reply_markup"))

    message.reply_text = capture_reply

    update = MagicMock()
    update.message = message
    update.effective_user.id = 1

    context = MagicMock()
    context.user_data = {"current_directory": root1}
    context.bot_data = {}

    await orchestrator.agentic_repo(update, context)

    assert reply_markup_holder, "reply_markup was not passed"
    markup = reply_markup_holder[0]
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    callback_datas = [btn.callback_data for btn in buttons]

    # Callback data must use root names, not integers
    for cd in callback_datas:
        parts = cd.split(":")
        assert len(parts) == 3, f"Expected cd:<root_name>:<dir> but got {cd!r}"
        assert not parts[
            1
        ].isdigit(), f"Root identifier should be a name, not an index: {cd!r}"
