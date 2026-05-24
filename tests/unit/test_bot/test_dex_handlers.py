"""Tests for Dex decision-queue command handlers.

Covers:
- /yes appends a Resolution block with status: resolved-yes
- /no appends a Resolution block with status: resolved-no
- /yes <unknown-id> replies with a not-found message
- /<custom-verb> appends a Resolution block with status: resolved-<verb>
- /yes <id> /now triggers _fire_now_dex (mocked)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.dex_handlers import handle_custom_verb, handle_no, handle_yes


@pytest.fixture
def pending_dir(tmp_path, monkeypatch):
    """Point dex_handlers at a tmp dir and seed it with D042.md."""
    monkeypatch.setenv("DEX_PENDING_DIR", str(tmp_path))
    decision = tmp_path / "D042.md"
    decision.write_text(
        "---\nid: D042\ntype: approval\nstatus: pending\n---\n\n"
        "## Question\nTest?\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_yes_appends_resolution(pending_dir):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["D042"]
    await handle_yes(update, context)
    content = (pending_dir / "D042.md").read_text(encoding="utf-8")
    assert "## Resolution" in content
    assert "status: resolved-yes" in content
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_no_appends_resolution(pending_dir):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["D042"]
    await handle_no(update, context)
    content = (pending_dir / "D042.md").read_text(encoding="utf-8")
    assert "status: resolved-no" in content


@pytest.mark.asyncio
async def test_yes_unknown_id_replies_error(pending_dir):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["D999"]
    await handle_yes(update, context)
    update.message.reply_text.assert_called_once()
    msg = update.message.reply_text.call_args[0][0]
    assert "not found" in msg.lower()


@pytest.mark.asyncio
async def test_revive_custom_verb(pending_dir):
    (pending_dir / "D050.md").write_text(
        "---\nid: D050\ntype: approval\nstatus: pending\n---\n",
        encoding="utf-8",
    )
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["D050"]
    await handle_custom_verb("revive", update, context)
    content = (pending_dir / "D050.md").read_text(encoding="utf-8")
    assert "status: resolved-revive" in content


@pytest.mark.asyncio
async def test_yes_now_invokes_fire_now(pending_dir, monkeypatch):
    calls = []

    async def fake_fire():
        calls.append("fired")

    monkeypatch.setattr(
        "src.bot.dex_handlers._fire_now_dex", fake_fire
    )
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["D042", "/now"]
    await handle_yes(update, context)
    assert calls == ["fired"]
    content = (pending_dir / "D042.md").read_text(encoding="utf-8")
    assert "fire-now: true" in content
