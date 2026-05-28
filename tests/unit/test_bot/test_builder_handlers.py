import pytest
from unittest.mock import AsyncMock, MagicMock
from src.bot.builder_handlers import handle_builder_status, handle_builder_kill, handle_builder_queue

@pytest.fixture
def builder_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDER_DATA_DIR", str(tmp_path))
    (tmp_path / "state.json").write_text('{"stage":"IMPLEMENT","ticket_id":"B001","ticks_used":3,"implement_attempts":0}', encoding="utf-8")
    (tmp_path / "queue").mkdir()
    (tmp_path / "queue" / "B002.md").write_text("---\nid: B002\n---\n", encoding="utf-8")
    return tmp_path

@pytest.mark.asyncio
async def test_status_reports_inflight(builder_dirs):
    u = MagicMock(); u.message.reply_text = AsyncMock(); ctx = MagicMock()
    await handle_builder_status(u, ctx)
    msg = u.message.reply_text.call_args[0][0]
    assert "B001" in msg and "IMPLEMENT" in msg

@pytest.mark.asyncio
async def test_kill_writes_kill_flag(builder_dirs):
    u = MagicMock(); u.message.reply_text = AsyncMock(); ctx = MagicMock(); ctx.args = ["B001"]
    await handle_builder_kill(u, ctx)
    assert "kill_requested" in (builder_dirs / "state.json").read_text(encoding="utf-8")

@pytest.mark.asyncio
async def test_queue_lists_pending(builder_dirs):
    u = MagicMock(); u.message.reply_text = AsyncMock(); ctx = MagicMock()
    await handle_builder_queue(u, ctx)
    assert "B002" in u.message.reply_text.call_args[0][0]
