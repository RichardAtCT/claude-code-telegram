"""Tests for the DraftStreamer module.

Covers:
- Text accumulation and retrieval
- Tool line accumulation and composition
- Throttle interval respected
- 4096-char truncation with ellipsis prefix
- Self-disabling on API error
- flush() force-sends immediately
- Draft ID generation is non-zero
- Integration with orchestrator callback
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.utils.draft_streamer import (
    DraftStreamer,
    _MAX_TOOL_LINES,
    generate_draft_id,
)
from src.utils.constants import TELEGRAM_MAX_MESSAGE_LENGTH

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.send_message_draft = AsyncMock()
    return bot


@pytest.fixture
def streamer(mock_bot):
    return DraftStreamer(
        bot=mock_bot,
        chat_id=123,
        draft_id=42,
        throttle_interval=0.3,
    )


# ---------------------------------------------------------------------------
# generate_draft_id
# ---------------------------------------------------------------------------


class TestGenerateDraftId:
    def test_non_zero(self):
        """Draft ID must always be non-zero."""
        for _ in range(100):
            did = generate_draft_id(123)
            assert did != 0

    def test_positive(self):
        """Draft ID must be positive."""
        for _ in range(100):
            did = generate_draft_id(456)
            assert did > 0

    def test_different_chats_differ(self):
        """Different chat IDs should generally produce different draft IDs."""
        ids = {generate_draft_id(i) for i in range(50)}
        # Not all identical (statistical — extremely unlikely to fail)
        assert len(ids) > 1


# ---------------------------------------------------------------------------
# DraftStreamer basics
# ---------------------------------------------------------------------------


class TestDraftStreamerAccumulation:
    async def test_append_accumulates_text(self, streamer, mock_bot):
        """Text is accumulated internally."""
        # First call within throttle — send happens immediately (last_send_time=0)
        await streamer.append_text("Hello ")
        assert streamer._accumulated_text == "Hello "
        mock_bot.send_message_draft.assert_called_once()

    async def test_append_empty_string_ignored(self, streamer, mock_bot):
        """Empty string should not trigger a send."""
        await streamer.append_text("")
        mock_bot.send_message_draft.assert_not_called()

    async def test_append_when_disabled(self, streamer, mock_bot):
        """Disabled streamer should not accumulate or send."""
        streamer._enabled = False
        await streamer.append_text("test")
        assert streamer._accumulated_text == ""
        mock_bot.send_message_draft.assert_not_called()


class TestDraftStreamerThrottle:
    async def test_throttle_prevents_rapid_sends(self, streamer, mock_bot):
        """Second append within throttle interval should not trigger send."""
        await streamer.append_text("first")
        mock_bot.send_message_draft.reset_mock()

        # Immediately append again — within throttle
        await streamer.append_text(" second")
        mock_bot.send_message_draft.assert_not_called()
        assert streamer._accumulated_text == "first second"

    async def test_sends_after_throttle_interval(self, streamer, mock_bot):
        """Send should happen once throttle interval has elapsed."""
        await streamer.append_text("first")
        mock_bot.send_message_draft.reset_mock()

        # Simulate time passing beyond throttle
        streamer._last_send_time = time.time() - 1.0
        await streamer.append_text(" second")
        mock_bot.send_message_draft.assert_called_once()
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["text"] == "first second"


class TestDraftStreamerTruncation:
    async def test_long_text_truncated_with_ellipsis(self, streamer, mock_bot):
        """Text longer than 4096 chars should be tail-truncated with ellipsis."""
        long_text = "x" * 5000
        streamer._accumulated_text = long_text
        await streamer.flush()

        call_kwargs = mock_bot.send_message_draft.call_args[1]
        sent_text = call_kwargs["text"]
        assert len(sent_text) == TELEGRAM_MAX_MESSAGE_LENGTH
        assert sent_text[0] == "\u2026"
        # The rest should be the tail of the original
        assert sent_text[1:] == long_text[-(4096 - 1) :]

    async def test_exact_limit_not_truncated(self, streamer, mock_bot):
        """Text exactly at limit should not be truncated."""
        exact_text = "y" * TELEGRAM_MAX_MESSAGE_LENGTH
        streamer._accumulated_text = exact_text
        await streamer.flush()

        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["text"] == exact_text


class TestDraftStreamerSelfDisable:
    async def test_api_error_disables_streamer(self, streamer, mock_bot):
        """API error should disable the streamer silently."""
        mock_bot.send_message_draft.side_effect = Exception("API error")
        await streamer.append_text("test")
        assert not streamer._enabled

    async def test_subsequent_sends_skipped_after_disable(self, streamer, mock_bot):
        """After disabling, no more sends should happen."""
        mock_bot.send_message_draft.side_effect = Exception("API error")
        await streamer.append_text("first")
        mock_bot.send_message_draft.reset_mock()
        mock_bot.send_message_draft.side_effect = None

        await streamer.append_text("second")
        mock_bot.send_message_draft.assert_not_called()


class TestDraftStreamerFlush:
    async def test_flush_sends_immediately(self, streamer, mock_bot):
        """flush() should send the current text regardless of throttle."""
        streamer._accumulated_text = "buffered text"
        streamer._last_send_time = time.time()  # pretend we just sent
        await streamer.flush()
        mock_bot.send_message_draft.assert_called_once()
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["text"] == "buffered text"

    async def test_flush_empty_is_noop(self, streamer, mock_bot):
        """flush() with no accumulated text should be a no-op."""
        await streamer.flush()
        mock_bot.send_message_draft.assert_not_called()

    async def test_flush_whitespace_only_is_noop(self, streamer, mock_bot):
        """flush() with only whitespace should be a no-op."""
        streamer._accumulated_text = "   \n\t  "
        await streamer.flush()
        mock_bot.send_message_draft.assert_not_called()

    async def test_flush_when_disabled_is_noop(self, streamer, mock_bot):
        """flush() should not send when streamer is disabled."""
        streamer._enabled = False
        streamer._accumulated_text = "some text"
        await streamer.flush()
        mock_bot.send_message_draft.assert_not_called()


class TestDraftStreamerThreadId:
    async def test_thread_id_passed_when_set(self, mock_bot):
        """message_thread_id should be included in the API call."""
        streamer = DraftStreamer(
            bot=mock_bot,
            chat_id=123,
            draft_id=42,
            message_thread_id=999,
        )
        await streamer.append_text("hello")
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["message_thread_id"] == 999

    async def test_thread_id_omitted_when_none(self, mock_bot):
        """message_thread_id should not be in kwargs when None."""
        streamer = DraftStreamer(
            bot=mock_bot,
            chat_id=123,
            draft_id=42,
            message_thread_id=None,
        )
        await streamer.append_text("hello")
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert "message_thread_id" not in call_kwargs


# ---------------------------------------------------------------------------
# Tool lines
# ---------------------------------------------------------------------------


class TestDraftStreamerToolLines:
    async def test_append_tool_sends_draft(self, streamer, mock_bot):
        """append_tool should trigger a draft send (first call, throttle=0)."""
        await streamer.append_tool("\U0001f4d6 Read")
        mock_bot.send_message_draft.assert_called_once()
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["text"] == "\U0001f4d6 Read"

    async def test_append_tool_empty_ignored(self, streamer, mock_bot):
        """Empty tool line should not trigger a send."""
        await streamer.append_tool("")
        mock_bot.send_message_draft.assert_not_called()

    async def test_append_tool_when_disabled(self, streamer, mock_bot):
        """Disabled streamer should not accumulate tools."""
        streamer._enabled = False
        await streamer.append_tool("\U0001f527 Grep")
        assert streamer._tool_lines == []
        mock_bot.send_message_draft.assert_not_called()

    async def test_tool_throttle(self, streamer, mock_bot):
        """Second tool within throttle should not trigger send."""
        await streamer.append_tool("\U0001f4d6 Read")
        mock_bot.send_message_draft.reset_mock()

        await streamer.append_tool("\U0001f527 Grep")
        mock_bot.send_message_draft.assert_not_called()
        assert len(streamer._tool_lines) == 2


class TestDraftStreamerComposition:
    async def test_tools_only(self, streamer, mock_bot):
        """Draft with only tool lines shows just tools."""
        streamer._tool_lines = ["\U0001f4d6 Read", "\U0001f527 Grep"]
        await streamer.flush()
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["text"] == "\U0001f4d6 Read\n\U0001f527 Grep"

    async def test_text_only(self, streamer, mock_bot):
        """Draft with only text shows just text (no separator)."""
        streamer._accumulated_text = "Hello world"
        await streamer.flush()
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["text"] == "Hello world"

    async def test_tools_plus_text(self, streamer, mock_bot):
        """Draft with both tools and text shows tools, blank line, text."""
        streamer._tool_lines = ["\U0001f4d6 Read"]
        streamer._accumulated_text = "Response text"
        await streamer.flush()
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        assert call_kwargs["text"] == "\U0001f4d6 Read\n\nResponse text"

    async def test_tool_overflow_shows_count(self, streamer, mock_bot):
        """More than _MAX_TOOL_LINES tools shows overflow count."""
        streamer._tool_lines = [f"tool_{i}" for i in range(_MAX_TOOL_LINES + 5)]
        await streamer.flush()
        call_kwargs = mock_bot.send_message_draft.call_args[1]
        text = call_kwargs["text"]
        assert text.startswith("... +5 more")
        # Should show the last _MAX_TOOL_LINES entries
        assert f"tool_{_MAX_TOOL_LINES + 4}" in text

    async def test_flush_tools_only_sends(self, streamer, mock_bot):
        """flush() with only tool lines should still send."""
        streamer._tool_lines = ["\U0001f4d6 Read"]
        streamer._last_send_time = time.time()
        await streamer.flush()
        mock_bot.send_message_draft.assert_called_once()
