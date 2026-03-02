"""Tests for the interactive questions module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.features.interactive_questions import (
    PendingQuestion,
    TelegramContext,
    askq_callback,
    askq_other_text,
    build_multi_select_keyboard,
    build_single_select_keyboard,
    cancel_pending,
    format_question_text,
    get_pending,
    make_ask_user_hook,
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


# ---------------------------------------------------------------------------
# Helpers for callback / hook tests
# ---------------------------------------------------------------------------


def _make_tg_ctx(user_id: int = 7, chat_id: int = 100, thread_id: int = None):
    """Build a TelegramContext with an AsyncMock bot."""
    bot = AsyncMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 42
    bot.send_message.return_value = sent_msg
    return TelegramContext(bot=bot, chat_id=chat_id, thread_id=thread_id, user_id=user_id)


def _make_update_with_callback(data: str, user_id: int = 7, chat_id: int = 100):
    """Build a minimal Update with a callback_query."""
    update = MagicMock(spec=["callback_query", "message"])
    update.message = None

    query = AsyncMock()
    query.data = data
    query.from_user = MagicMock()
    query.from_user.id = user_id
    query.message = MagicMock()
    query.message.chat = MagicMock()
    query.message.chat.id = chat_id
    update.callback_query = query
    return update


def _make_update_with_text(text: str, user_id: int = 7, chat_id: int = 100):
    """Build a minimal Update with a text message."""
    update = MagicMock(spec=["callback_query", "message"])
    update.callback_query = None

    message = MagicMock()
    message.text = text
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    update.message = message
    return update


# ---------------------------------------------------------------------------
# make_ask_user_hook
# ---------------------------------------------------------------------------


class TestMakeAskUserHook:
    @pytest.mark.asyncio
    async def test_non_ask_user_question_returns_empty(self):
        tg_ctx = _make_tg_ctx()
        hook = make_ask_user_hook(tg_ctx)
        result = await hook(
            {"tool_name": "Bash", "tool_input": {}},
            tool_use_id="t1",
            context={},
        )
        assert result == {}
        tg_ctx.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_keyboard_and_returns_updated_input(self):
        tg_ctx = _make_tg_ctx()
        hook = make_ask_user_hook(tg_ctx)

        tool_input = {
            "questions": [
                {
                    "question": "Continue?",
                    "options": [{"label": "Yes"}, {"label": "No"}],
                    "multiSelect": False,
                }
            ]
        }

        async def resolve_after_delay():
            """Wait briefly then resolve the pending question."""
            await asyncio.sleep(0.05)
            pq = get_pending(tg_ctx.user_id, tg_ctx.chat_id)
            assert pq is not None
            resolve_pending(tg_ctx.user_id, tg_ctx.chat_id, "Yes")

        task = asyncio.create_task(resolve_after_delay())
        result = await hook(
            {"tool_name": "AskUserQuestion", "tool_input": tool_input},
            tool_use_id="t2",
            context={},
        )
        await task

        tg_ctx.bot.send_message.assert_called_once()
        call_kwargs = tg_ctx.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == tg_ctx.chat_id
        assert "reply_markup" in call_kwargs

        assert result == {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {**tool_input, "answers": {"Continue?": "Yes"}},
            }
        }

    @pytest.mark.asyncio
    async def test_multiple_questions_processed_sequentially(self):
        tg_ctx = _make_tg_ctx()
        hook = make_ask_user_hook(tg_ctx)

        tool_input = {
            "questions": [
                {
                    "question": "First?",
                    "options": [{"label": "A"}],
                    "multiSelect": False,
                },
                {
                    "question": "Second?",
                    "options": [{"label": "B"}],
                    "multiSelect": False,
                },
            ]
        }

        resolve_order = []

        async def resolve_questions():
            for expected_q, answer in [("First?", "A"), ("Second?", "B")]:
                # Wait for the pending question to appear
                for _ in range(50):
                    pq = get_pending(tg_ctx.user_id, tg_ctx.chat_id)
                    if pq is not None and pq.question_text == expected_q:
                        break
                    await asyncio.sleep(0.02)
                resolve_order.append(expected_q)
                resolve_pending(tg_ctx.user_id, tg_ctx.chat_id, answer)

        task = asyncio.create_task(resolve_questions())
        result = await hook(
            {"tool_name": "AskUserQuestion", "tool_input": tool_input},
            tool_use_id="t3",
            context={},
        )
        await task

        assert resolve_order == ["First?", "Second?"]
        answers = result["hookSpecificOutput"]["updatedInput"]["answers"]
        assert answers == {"First?": "A", "Second?": "B"}
        assert tg_ctx.bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_send_failure_cancels_and_returns_empty(self):
        tg_ctx = _make_tg_ctx()
        tg_ctx.bot.send_message.side_effect = Exception("network error")
        hook = make_ask_user_hook(tg_ctx)

        tool_input = {
            "questions": [
                {
                    "question": "Fail?",
                    "options": [{"label": "X"}],
                    "multiSelect": False,
                }
            ]
        }

        result = await hook(
            {"tool_name": "AskUserQuestion", "tool_input": tool_input},
            tool_use_id="t4",
            context={},
        )
        assert result == {}
        assert get_pending(tg_ctx.user_id, tg_ctx.chat_id) is None

    @pytest.mark.asyncio
    async def test_thread_id_passed_when_set(self):
        tg_ctx = _make_tg_ctx(thread_id=55)
        hook = make_ask_user_hook(tg_ctx)

        tool_input = {
            "questions": [
                {
                    "question": "Thread?",
                    "options": [{"label": "Ok"}],
                    "multiSelect": False,
                }
            ]
        }

        async def resolve_after_delay():
            await asyncio.sleep(0.05)
            resolve_pending(tg_ctx.user_id, tg_ctx.chat_id, "Ok")

        task = asyncio.create_task(resolve_after_delay())
        await hook(
            {"tool_name": "AskUserQuestion", "tool_input": tool_input},
            tool_use_id="t5",
            context={},
        )
        await task

        call_kwargs = tg_ctx.bot.send_message.call_args.kwargs
        assert call_kwargs["message_thread_id"] == 55


# ---------------------------------------------------------------------------
# askq_callback
# ---------------------------------------------------------------------------


class TestAskqCallback:
    @pytest.mark.asyncio
    async def test_single_select_resolves_with_label(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick one",
            options=[{"label": "Alpha"}, {"label": "Beta"}],
            multi_select=False,
        )
        register_pending(user_id=7, chat_id=100, pq=pq)

        update = _make_update_with_callback("askq:0:1", user_id=7, chat_id=100)
        await askq_callback(update, MagicMock())

        assert future.done()
        assert future.result() == "Beta"
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_text.assert_awaited_once_with("✓ Beta")

    @pytest.mark.asyncio
    async def test_multi_select_toggle_updates_selected(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick many",
            options=[{"label": "A"}, {"label": "B"}, {"label": "C"}],
            multi_select=True,
        )
        register_pending(user_id=7, chat_id=100, pq=pq)

        # Toggle index 1
        update = _make_update_with_callback("askq:0:t1", user_id=7, chat_id=100)
        await askq_callback(update, MagicMock())

        assert 1 in pq.selected
        assert not future.done()
        update.callback_query.edit_message_reply_markup.assert_awaited_once()

        # Toggle index 1 again to deselect
        update2 = _make_update_with_callback("askq:0:t1", user_id=7, chat_id=100)
        await askq_callback(update2, MagicMock())

        assert 1 not in pq.selected

    @pytest.mark.asyncio
    async def test_multi_select_done_resolves_with_joined_labels(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick many",
            options=[{"label": "X"}, {"label": "Y"}, {"label": "Z"}],
            multi_select=True,
            selected={0, 2},
        )
        register_pending(user_id=7, chat_id=100, pq=pq)

        update = _make_update_with_callback("askq:0:done", user_id=7, chat_id=100)
        await askq_callback(update, MagicMock())

        assert future.done()
        assert future.result() == "X, Z"
        update.callback_query.edit_message_text.assert_awaited_once_with("✓ X, Z")

    @pytest.mark.asyncio
    async def test_other_sets_awaiting_other(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick one",
            options=[{"label": "A"}],
            multi_select=False,
        )
        register_pending(user_id=7, chat_id=100, pq=pq)

        update = _make_update_with_callback("askq:0:other", user_id=7, chat_id=100)
        await askq_callback(update, MagicMock())

        assert pq.awaiting_other is True
        assert not future.done()
        update.callback_query.edit_message_text.assert_awaited_once_with(
            "Type your answer:"
        )

    @pytest.mark.asyncio
    async def test_expired_question_shows_alert(self):
        update = _make_update_with_callback("askq:0:0", user_id=7, chat_id=100)
        await askq_callback(update, MagicMock())

        update.callback_query.answer.assert_awaited_once_with(
            "Question expired.", show_alert=True
        )


# ---------------------------------------------------------------------------
# askq_other_text
# ---------------------------------------------------------------------------


class TestAskqOtherText:
    @pytest.mark.asyncio
    async def test_captures_text_when_awaiting_other(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick",
            options=[{"label": "A"}],
            multi_select=False,
            awaiting_other=True,
        )
        register_pending(user_id=7, chat_id=100, pq=pq)

        update = _make_update_with_text("custom answer", user_id=7, chat_id=100)
        result = await askq_other_text(update, MagicMock())

        assert result is True
        assert future.done()
        assert future.result() == "custom answer"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_pending(self):
        update = _make_update_with_text("hello", user_id=7, chat_id=100)
        result = await askq_other_text(update, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_awaiting_other(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick",
            options=[{"label": "A"}],
            multi_select=False,
            awaiting_other=False,
        )
        register_pending(user_id=7, chat_id=100, pq=pq)

        update = _make_update_with_text("hello", user_id=7, chat_id=100)
        result = await askq_other_text(update, MagicMock())

        assert result is None
        assert not future.done()
