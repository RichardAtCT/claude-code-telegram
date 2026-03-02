"""Tests for the interactive questions module."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.bot.features.interactive_questions import (
    PendingQuestion,
    TelegramContext,
    build_multi_select_keyboard,
    build_single_select_keyboard,
    cancel_pending,
    format_question_text,
    get_pending,
    register_pending,
    resolve_pending,
    _pending,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_registry():
    """Ensure the pending registry is clean for each test."""
    _pending.clear()
    yield
    _pending.clear()


@pytest.fixture
def sample_options():
    """Sample option dicts used across tests."""
    return [
        {"label": "Yes", "description": "Accept the change"},
        {"label": "No", "description": "Reject the change"},
        {"label": "Skip"},
    ]


@pytest.fixture
def sample_options_no_desc():
    """Options with no descriptions."""
    return [
        {"label": "Alpha"},
        {"label": "Beta"},
    ]


@pytest.fixture
def event_loop():
    """Provide a fresh event loop for Future creation."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _make_pending(loop: asyncio.AbstractEventLoop, **kwargs) -> PendingQuestion:
    """Helper to create a PendingQuestion with a Future on the given loop."""
    defaults = {
        "future": loop.create_future(),
        "question_text": "Pick one",
        "options": [{"label": "A"}, {"label": "B"}],
        "multi_select": False,
    }
    defaults.update(kwargs)
    return PendingQuestion(**defaults)


# ---------------------------------------------------------------------------
# TelegramContext
# ---------------------------------------------------------------------------


class TestTelegramContext:
    def test_creation_with_thread(self):
        ctx = TelegramContext(bot=MagicMock(), chat_id=100, thread_id=42, user_id=7)
        assert ctx.chat_id == 100
        assert ctx.thread_id == 42
        assert ctx.user_id == 7

    def test_creation_without_thread(self):
        ctx = TelegramContext(bot=MagicMock(), chat_id=100, thread_id=None, user_id=7)
        assert ctx.thread_id is None


# ---------------------------------------------------------------------------
# PendingQuestion
# ---------------------------------------------------------------------------


class TestPendingQuestion:
    def test_defaults(self, event_loop):
        pq = _make_pending(event_loop)
        assert pq.selected == set()
        assert pq.message_id is None
        assert pq.awaiting_other is False

    def test_custom_fields(self, event_loop):
        pq = _make_pending(
            event_loop,
            multi_select=True,
            selected={0, 2},
            message_id=999,
            awaiting_other=True,
        )
        assert pq.multi_select is True
        assert pq.selected == {0, 2}
        assert pq.message_id == 999
        assert pq.awaiting_other is True


# ---------------------------------------------------------------------------
# format_question_text
# ---------------------------------------------------------------------------


class TestFormatQuestionText:
    def test_with_descriptions(self, sample_options):
        text = format_question_text("Choose wisely", sample_options)
        assert text.startswith("**Choose wisely**")
        assert "• Yes — Accept the change" in text
        assert "• No — Reject the change" in text
        # "Skip" has no description, so no dash
        assert "• Skip" in text
        assert "Skip —" not in text

    def test_without_descriptions(self, sample_options_no_desc):
        text = format_question_text("Pick", sample_options_no_desc)
        assert "• Alpha" in text
        assert "• Beta" in text
        # No dash at all
        assert "—" not in text

    def test_empty_options(self):
        text = format_question_text("Nothing?", [])
        assert text == "**Nothing?**\n"


# ---------------------------------------------------------------------------
# build_single_select_keyboard
# ---------------------------------------------------------------------------


class TestBuildSingleSelectKeyboard:
    def test_buttons_match_options(self, sample_options):
        kb = build_single_select_keyboard(sample_options, question_idx=0)
        # Flatten all buttons
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        labels = [btn.text for btn in all_buttons]
        assert "Yes" in labels
        assert "No" in labels
        assert "Skip" in labels
        assert "Other..." in labels

    def test_callback_data_format(self, sample_options):
        kb = build_single_select_keyboard(sample_options, question_idx=5)
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        # Option buttons have askq:<idx>:<option_num>
        option_buttons = [b for b in all_buttons if b.text not in ("Other...",)]
        for i, btn in enumerate(option_buttons):
            assert btn.callback_data == f"askq:5:{i}"

    def test_other_button_present(self, sample_options):
        kb = build_single_select_keyboard(sample_options, question_idx=0)
        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 1
        assert last_row[0].text == "Other..."
        assert last_row[0].callback_data == "askq:0:other"

    def test_two_per_row_layout(self):
        """Options are laid out 2 per row, plus the Other row."""
        options = [{"label": f"Opt{i}"} for i in range(5)]
        kb = build_single_select_keyboard(options, question_idx=0)
        # 5 options -> 3 rows of options (2, 2, 1), + 1 Other row = 4 rows
        assert len(kb.inline_keyboard) == 4
        assert len(kb.inline_keyboard[0]) == 2
        assert len(kb.inline_keyboard[1]) == 2
        assert len(kb.inline_keyboard[2]) == 1
        assert len(kb.inline_keyboard[3]) == 1  # Other

    def test_fallback_label(self):
        """Options missing 'label' get a fallback."""
        options = [{}]
        kb = build_single_select_keyboard(options, question_idx=0)
        option_btn = kb.inline_keyboard[0][0]
        assert option_btn.text == "Option 0"


# ---------------------------------------------------------------------------
# build_multi_select_keyboard
# ---------------------------------------------------------------------------


class TestBuildMultiSelectKeyboard:
    def test_unchecked_by_default(self, sample_options):
        kb = build_multi_select_keyboard(sample_options, question_idx=0, selected=set())
        option_buttons = [
            btn
            for row in kb.inline_keyboard
            for btn in row
            if btn.text not in ("Other...", "Done ✓")
        ]
        for btn in option_buttons:
            assert btn.text.startswith("☐")

    def test_checked_state(self, sample_options):
        kb = build_multi_select_keyboard(sample_options, question_idx=0, selected={0, 2})
        option_buttons = [
            btn
            for row in kb.inline_keyboard
            for btn in row
            if btn.text not in ("Other...", "Done ✓")
        ]
        assert option_buttons[0].text.startswith("☑")  # index 0 selected
        assert option_buttons[1].text.startswith("☐")  # index 1 not selected
        assert option_buttons[2].text.startswith("☑")  # index 2 selected

    def test_toggle_callback_data(self, sample_options):
        kb = build_multi_select_keyboard(sample_options, question_idx=3, selected=set())
        option_buttons = [
            btn
            for row in kb.inline_keyboard
            for btn in row
            if btn.text not in ("Other...", "Done ✓")
        ]
        for i, btn in enumerate(option_buttons):
            assert btn.callback_data == f"askq:3:t{i}"

    def test_done_button(self, sample_options):
        kb = build_multi_select_keyboard(sample_options, question_idx=0, selected=set())
        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 1
        assert last_row[0].text == "Done ✓"
        assert last_row[0].callback_data == "askq:0:done"

    def test_other_button(self, sample_options):
        kb = build_multi_select_keyboard(sample_options, question_idx=0, selected=set())
        # Other is second-to-last row
        other_row = kb.inline_keyboard[-2]
        assert len(other_row) == 1
        assert other_row[0].text == "Other..."
        assert other_row[0].callback_data == "askq:0:other"

    def test_fallback_label(self):
        """Options missing 'label' get a fallback with checkbox prefix."""
        options = [{}]
        kb = build_multi_select_keyboard(options, question_idx=0, selected=set())
        option_btn = kb.inline_keyboard[0][0]
        assert option_btn.text == "☐ Option 0"


# ---------------------------------------------------------------------------
# Pending registry
# ---------------------------------------------------------------------------


class TestPendingRegistry:
    def test_register_and_get(self, event_loop):
        pq = _make_pending(event_loop)
        register_pending(user_id=1, chat_id=2, pq=pq)
        assert get_pending(1, 2) is pq

    def test_get_missing_returns_none(self):
        assert get_pending(999, 999) is None

    def test_resolve_clears_and_sets_result(self, event_loop):
        pq = _make_pending(event_loop)
        register_pending(user_id=1, chat_id=2, pq=pq)

        resolve_pending(1, 2, "user_answer")

        assert get_pending(1, 2) is None
        assert pq.future.done()
        assert pq.future.result() == "user_answer"

    def test_cancel_clears_and_cancels_future(self, event_loop):
        pq = _make_pending(event_loop)
        register_pending(user_id=1, chat_id=2, pq=pq)

        cancel_pending(1, 2)

        assert get_pending(1, 2) is None
        assert pq.future.cancelled()

    def test_resolve_missing_is_noop(self):
        # Should not raise
        resolve_pending(999, 999, "anything")

    def test_cancel_missing_is_noop(self):
        # Should not raise
        cancel_pending(999, 999)

    def test_resolve_already_done_is_noop(self, event_loop):
        pq = _make_pending(event_loop)
        pq.future.set_result("first")
        register_pending(user_id=1, chat_id=2, pq=pq)

        # Should not raise even though future is already done
        resolve_pending(1, 2, "second")
        assert pq.future.result() == "first"

    def test_cancel_already_done_is_noop(self, event_loop):
        pq = _make_pending(event_loop)
        pq.future.set_result("done")
        register_pending(user_id=1, chat_id=2, pq=pq)

        # Should not raise even though future is already done
        cancel_pending(1, 2)
        assert pq.future.result() == "done"
        assert not pq.future.cancelled()

    def test_register_overwrites_existing(self, event_loop):
        pq1 = _make_pending(event_loop, question_text="first")
        pq2 = _make_pending(event_loop, question_text="second")
        register_pending(user_id=1, chat_id=2, pq=pq1)
        register_pending(user_id=1, chat_id=2, pq=pq2)
        assert get_pending(1, 2) is pq2
