# Interactive User Feedback Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Intercept `AskUserQuestion` tool calls via PreToolUse SDK hooks and route them through Telegram inline keyboards so users can answer interactively.

**Architecture:** A PreToolUse hook on `AskUserQuestion` pauses Claude, sends the question as Telegram inline buttons, awaits user tap via `asyncio.Future`, then returns the answer as `updatedInput`. A shared `_pending` dict keyed by `(user_id, chat_id)` coordinates the hook callback and the Telegram `CallbackQueryHandler`.

**Tech Stack:** `claude-agent-sdk` (PreToolUse hooks, HookMatcher, SyncHookJSONOutput), `python-telegram-bot` (InlineKeyboardMarkup, CallbackQueryHandler, MessageHandler), `asyncio.Future`

---

### Task 1: Create interactive_questions module — data types and pending registry

**Files:**
- Create: `src/bot/features/interactive_questions.py`
- Test: `tests/unit/test_bot/test_interactive_questions.py`

**Step 1: Write the failing tests**

```python
"""Tests for interactive_questions module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.features.interactive_questions import (
    PendingQuestion,
    TelegramContext,
    format_question_text,
    build_single_select_keyboard,
    build_multi_select_keyboard,
    register_pending,
    resolve_pending,
    get_pending,
    cancel_pending,
)


class TestTelegramContext:
    def test_creation(self):
        bot = MagicMock()
        ctx = TelegramContext(bot=bot, chat_id=123, thread_id=456, user_id=789)
        assert ctx.bot is bot
        assert ctx.chat_id == 123
        assert ctx.thread_id == 456
        assert ctx.user_id == 789

    def test_thread_id_optional(self):
        bot = MagicMock()
        ctx = TelegramContext(bot=bot, chat_id=123, thread_id=None, user_id=789)
        assert ctx.thread_id is None


class TestPendingQuestion:
    def test_creation(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Which?",
            options=[{"label": "A", "description": "opt A"}],
            multi_select=False,
            selected=set(),
            message_id=None,
        )
        assert pq.question_text == "Which?"
        assert pq.multi_select is False
        assert pq.selected == set()
        loop.close()


class TestFormatQuestionText:
    def test_basic_formatting(self):
        options = [
            {"label": "Alpha", "description": "First option"},
            {"label": "Beta", "description": "Second option"},
        ]
        text = format_question_text("Pick one?", options)
        assert "Pick one?" in text
        assert "Alpha" in text
        assert "First option" in text
        assert "Beta" in text

    def test_no_description(self):
        options = [{"label": "X"}, {"label": "Y"}]
        text = format_question_text("Choose", options)
        assert "X" in text
        assert "Y" in text


class TestBuildSingleSelectKeyboard:
    def test_buttons_match_options(self):
        options = [
            {"label": "A", "description": "opt A"},
            {"label": "B", "description": "opt B"},
        ]
        kb = build_single_select_keyboard(options, question_idx=0)
        # Flatten all buttons
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        labels = [btn.text for btn in buttons]
        assert "A" in labels
        assert "B" in labels
        assert "Other..." in labels

    def test_callback_data_format(self):
        options = [{"label": "A", "description": "x"}]
        kb = build_single_select_keyboard(options, question_idx=2)
        btn = kb.inline_keyboard[0][0]
        assert btn.callback_data == "askq:2:0"

    def test_other_button(self):
        options = [{"label": "A", "description": "x"}]
        kb = build_single_select_keyboard(options, question_idx=0)
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        other = [b for b in buttons if b.callback_data == "askq:0:other"]
        assert len(other) == 1


class TestBuildMultiSelectKeyboard:
    def test_unchecked_by_default(self):
        options = [
            {"label": "A", "description": "x"},
            {"label": "B", "description": "y"},
        ]
        kb = build_multi_select_keyboard(options, question_idx=0, selected=set())
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert any("☐ A" == btn.text for btn in buttons)
        assert any("☐ B" == btn.text for btn in buttons)

    def test_checked_state(self):
        options = [
            {"label": "A", "description": "x"},
            {"label": "B", "description": "y"},
        ]
        kb = build_multi_select_keyboard(options, question_idx=0, selected={0})
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert any("☑ A" == btn.text for btn in buttons)
        assert any("☐ B" == btn.text for btn in buttons)

    def test_toggle_callback_data(self):
        options = [{"label": "A", "description": "x"}]
        kb = build_multi_select_keyboard(options, question_idx=1, selected=set())
        btn = kb.inline_keyboard[0][0]
        assert btn.callback_data == "askq:1:t0"

    def test_done_and_other_buttons(self):
        options = [{"label": "A", "description": "x"}]
        kb = build_multi_select_keyboard(options, question_idx=0, selected=set())
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        data = [b.callback_data for b in buttons]
        assert "askq:0:other" in data
        assert "askq:0:done" in data


class TestPendingRegistry:
    def test_register_and_get(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Q?",
            options=[],
            multi_select=False,
            selected=set(),
            message_id=None,
        )
        register_pending(789, 123, pq)
        assert get_pending(789, 123) is pq
        loop.close()

    def test_resolve_clears(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Q?",
            options=[],
            multi_select=False,
            selected=set(),
            message_id=None,
        )
        register_pending(789, 123, pq)
        resolve_pending(789, 123, "answer")
        assert future.result() == "answer"
        assert get_pending(789, 123) is None
        loop.close()

    def test_cancel_clears(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Q?",
            options=[],
            multi_select=False,
            selected=set(),
            message_id=None,
        )
        register_pending(789, 123, pq)
        cancel_pending(789, 123)
        assert future.cancelled()
        assert get_pending(789, 123) is None
        loop.close()

    def test_resolve_missing_is_noop(self):
        resolve_pending(999, 999, "x")  # Should not raise

    def test_cancel_missing_is_noop(self):
        cancel_pending(999, 999)  # Should not raise
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_bot/test_interactive_questions.py -v`
Expected: ImportError — module does not exist yet

**Step 3: Write the implementation**

```python
"""Interactive question routing for AskUserQuestion tool calls.

Intercepts AskUserQuestion via PreToolUse hooks and presents questions
as Telegram inline keyboards. Uses asyncio.Future to coordinate between
the hook callback (which pauses Claude) and the Telegram button handler.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = structlog.get_logger()


@dataclass
class TelegramContext:
    """Telegram context needed to send messages from the hook callback."""

    bot: Any  # telegram.Bot
    chat_id: int
    thread_id: Optional[int]
    user_id: int


@dataclass
class PendingQuestion:
    """A question waiting for user response."""

    future: asyncio.Future
    question_text: str
    options: List[Dict[str, Any]]
    multi_select: bool
    selected: Set[int]
    message_id: Optional[int]


# Module-level registry: (user_id, chat_id) → PendingQuestion
_pending: Dict[Tuple[int, int], PendingQuestion] = {}


def register_pending(user_id: int, chat_id: int, pq: PendingQuestion) -> None:
    """Register a pending question for a user+chat."""
    _pending[(user_id, chat_id)] = pq


def get_pending(user_id: int, chat_id: int) -> Optional[PendingQuestion]:
    """Get the pending question for a user+chat, if any."""
    return _pending.get((user_id, chat_id))


def resolve_pending(user_id: int, chat_id: int, answer: Any) -> None:
    """Resolve a pending question with the user's answer."""
    pq = _pending.pop((user_id, chat_id), None)
    if pq and not pq.future.done():
        pq.future.set_result(answer)


def cancel_pending(user_id: int, chat_id: int) -> None:
    """Cancel a pending question (e.g. on session error)."""
    pq = _pending.pop((user_id, chat_id), None)
    if pq and not pq.future.done():
        pq.future.cancel()


def format_question_text(question: str, options: List[Dict[str, Any]]) -> str:
    """Format a question with its options as readable text."""
    lines = [f"**{question}**", ""]
    for opt in options:
        label = opt.get("label", "")
        desc = opt.get("description", "")
        if desc:
            lines.append(f"• {label} — {desc}")
        else:
            lines.append(f"• {label}")
    return "\n".join(lines)


def build_single_select_keyboard(
    options: List[Dict[str, Any]], question_idx: int
) -> InlineKeyboardMarkup:
    """Build inline keyboard for a single-select question."""
    buttons = []
    for i, opt in enumerate(options):
        buttons.append(
            InlineKeyboardButton(
                text=opt.get("label", f"Option {i}"),
                callback_data=f"askq:{question_idx}:{i}",
            )
        )
    # Arrange in rows of 2
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    # Other button on its own row
    rows.append(
        [InlineKeyboardButton(text="Other...", callback_data=f"askq:{question_idx}:other")]
    )
    return InlineKeyboardMarkup(rows)


def build_multi_select_keyboard(
    options: List[Dict[str, Any]], question_idx: int, selected: Set[int]
) -> InlineKeyboardMarkup:
    """Build inline keyboard for a multi-select question."""
    buttons = []
    for i, opt in enumerate(options):
        label = opt.get("label", f"Option {i}")
        prefix = "☑" if i in selected else "☐"
        buttons.append(
            InlineKeyboardButton(
                text=f"{prefix} {label}",
                callback_data=f"askq:{question_idx}:t{i}",
            )
        )
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [InlineKeyboardButton(text="Other...", callback_data=f"askq:{question_idx}:other")]
    )
    rows.append(
        [InlineKeyboardButton(text="Done ✓", callback_data=f"askq:{question_idx}:done")]
    )
    return InlineKeyboardMarkup(rows)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_bot/test_interactive_questions.py -v`
Expected: All 18 tests PASS

**Step 5: Commit**

```bash
git add src/bot/features/interactive_questions.py tests/unit/test_bot/test_interactive_questions.py
git commit -m "feat: add interactive questions module with pending registry and keyboard builders"
```

---

### Task 2: Create the PreToolUse hook callback factory

**Files:**
- Modify: `src/bot/features/interactive_questions.py`
- Test: `tests/unit/test_bot/test_interactive_questions.py`

**Step 1: Write failing tests**

Add to `tests/unit/test_bot/test_interactive_questions.py`:

```python
from src.bot.features.interactive_questions import make_ask_user_hook


class TestMakeAskUserHook:
    @pytest.mark.asyncio
    async def test_non_ask_user_tool_passes_through(self):
        """Hook returns empty dict for non-AskUserQuestion tools."""
        ctx = TelegramContext(bot=MagicMock(), chat_id=1, thread_id=None, user_id=1)
        hook = make_ask_user_hook(ctx)
        result = await hook(
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}, "tool_use_id": "x", "session_id": "s", "transcript_path": "", "cwd": ""},
            "x",
            {"signal": None},
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_sends_keyboard_for_ask_user(self):
        """Hook sends inline keyboard to Telegram for AskUserQuestion."""
        bot = AsyncMock()
        sent_msg = MagicMock()
        sent_msg.message_id = 42
        bot.send_message.return_value = sent_msg

        ctx = TelegramContext(bot=bot, chat_id=100, thread_id=5, user_id=200)
        hook = make_ask_user_hook(ctx)

        tool_input = {
            "questions": [
                {
                    "question": "Pick one?",
                    "header": "Choice",
                    "options": [
                        {"label": "A", "description": "opt A"},
                        {"label": "B", "description": "opt B"},
                    ],
                    "multiSelect": False,
                }
            ]
        }

        # Run hook in background, resolve the pending future after send
        async def resolve_later():
            await asyncio.sleep(0.05)
            pq = get_pending(200, 100)
            assert pq is not None
            assert pq.message_id == 42
            resolve_pending(200, 100, "A")

        asyncio.get_event_loop().create_task(resolve_later())

        result = await hook(
            {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_input": tool_input, "tool_use_id": "t1", "session_id": "s", "transcript_path": "", "cwd": ""},
            "t1",
            {"signal": None},
        )

        # Verify keyboard was sent
        bot.send_message.assert_called_once()
        call_kwargs = bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 100
        assert call_kwargs["message_thread_id"] == 5
        assert "reply_markup" in call_kwargs

        # Verify updatedInput has the answer
        specific = result.get("hookSpecificOutput", {})
        assert specific["hookEventName"] == "PreToolUse"
        updated = specific["updatedInput"]
        assert updated["answers"]["Pick one?"] == "A"

    @pytest.mark.asyncio
    async def test_multi_question_sequential(self):
        """Hook processes multiple questions sequentially."""
        bot = AsyncMock()
        sent_msg = MagicMock()
        sent_msg.message_id = 10
        bot.send_message.return_value = sent_msg
        bot.edit_message_text.return_value = sent_msg

        ctx = TelegramContext(bot=bot, chat_id=100, thread_id=None, user_id=200)
        hook = make_ask_user_hook(ctx)

        tool_input = {
            "questions": [
                {
                    "question": "First?",
                    "header": "Q1",
                    "options": [{"label": "X", "description": ""}],
                    "multiSelect": False,
                },
                {
                    "question": "Second?",
                    "header": "Q2",
                    "options": [{"label": "Y", "description": ""}],
                    "multiSelect": False,
                },
            ]
        }

        async def resolve_both():
            await asyncio.sleep(0.05)
            resolve_pending(200, 100, "X")
            await asyncio.sleep(0.05)
            resolve_pending(200, 100, "Y")

        asyncio.get_event_loop().create_task(resolve_both())

        result = await hook(
            {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_input": tool_input, "tool_use_id": "t1", "session_id": "s", "transcript_path": "", "cwd": ""},
            "t1",
            {"signal": None},
        )

        answers = result["hookSpecificOutput"]["updatedInput"]["answers"]
        assert answers["First?"] == "X"
        assert answers["Second?"] == "Y"
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_bot/test_interactive_questions.py::TestMakeAskUserHook -v`
Expected: ImportError for `make_ask_user_hook`

**Step 3: Implement make_ask_user_hook**

Add to `src/bot/features/interactive_questions.py`:

```python
def make_ask_user_hook(tg_ctx: TelegramContext):
    """Create a PreToolUse hook callback that intercepts AskUserQuestion.

    The returned async function is registered as a PreToolUse hook in
    ClaudeAgentOptions.hooks. When Claude calls AskUserQuestion, the hook:
    1. Sends the question as Telegram inline keyboard buttons
    2. Awaits the user's tap via asyncio.Future
    3. Returns updatedInput with pre-filled answers
    """

    async def hook(
        input_data: Dict[str, Any],
        tool_use_id: Optional[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        if tool_name != "AskUserQuestion":
            return {}

        tool_input = input_data.get("tool_input", {})
        questions = tool_input.get("questions", [])
        if not questions:
            return {}

        answers: Dict[str, str] = {}

        for q_idx, q in enumerate(questions):
            question_text = q.get("question", "")
            options = q.get("options", [])
            multi_select = q.get("multiSelect", False)

            # Build keyboard and message text
            text = format_question_text(question_text, options)
            if multi_select:
                keyboard = build_multi_select_keyboard(options, q_idx, set())
            else:
                keyboard = build_single_select_keyboard(options, q_idx)

            # Create Future and register
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            pq = PendingQuestion(
                future=future,
                question_text=question_text,
                options=options,
                multi_select=multi_select,
                selected=set(),
                message_id=None,
            )
            register_pending(tg_ctx.user_id, tg_ctx.chat_id, pq)

            # Send question to Telegram
            try:
                msg = await tg_ctx.bot.send_message(
                    chat_id=tg_ctx.chat_id,
                    text=text,
                    reply_markup=keyboard,
                    message_thread_id=tg_ctx.thread_id,
                )
                pq.message_id = msg.message_id
            except Exception as e:
                logger.error("Failed to send question to Telegram", error=str(e))
                cancel_pending(tg_ctx.user_id, tg_ctx.chat_id)
                return {}

            # Wait for user's answer
            try:
                answer = await future
            except asyncio.CancelledError:
                logger.info("Question cancelled", question=question_text)
                return {}

            answers[question_text] = answer

            logger.info(
                "User answered question",
                question=question_text,
                answer=answer,
            )

        # Return updatedInput with pre-filled answers
        updated_input = {**tool_input, "answers": answers}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": updated_input,
            }
        }

    return hook
```

**Step 4: Run tests**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_bot/test_interactive_questions.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/bot/features/interactive_questions.py tests/unit/test_bot/test_interactive_questions.py
git commit -m "feat: add PreToolUse hook factory for AskUserQuestion interception"
```

---

### Task 3: Create the Telegram callback handler for askq: buttons

**Files:**
- Modify: `src/bot/features/interactive_questions.py`
- Test: `tests/unit/test_bot/test_interactive_questions.py`

**Step 1: Write failing tests**

Add to the test file:

```python
from src.bot.features.interactive_questions import askq_callback, askq_other_text


class TestAskqCallback:
    @pytest.mark.asyncio
    async def test_single_select_resolves(self):
        """Tapping a button resolves the pending question."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick?",
            options=[{"label": "A", "description": ""}, {"label": "B", "description": ""}],
            multi_select=False,
            selected=set(),
            message_id=42,
        )
        register_pending(200, 100, pq)

        query = AsyncMock()
        query.data = "askq:0:1"
        query.from_user.id = 200
        query.message.chat_id = 100
        query.message.message_id = 42
        query.message.message_thread_id = None

        update = MagicMock()
        update.callback_query = query

        context = MagicMock()

        await askq_callback(update, context)

        assert future.result() == "B"
        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_select_toggle(self):
        """Tapping a multi-select toggle updates keyboard."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick many?",
            options=[{"label": "A", "description": ""}, {"label": "B", "description": ""}],
            multi_select=True,
            selected=set(),
            message_id=42,
        )
        register_pending(200, 100, pq)

        query = AsyncMock()
        query.data = "askq:0:t0"
        query.from_user.id = 200
        query.message.chat_id = 100
        query.message.message_id = 42
        query.message.message_thread_id = None

        update = MagicMock()
        update.callback_query = query

        context = MagicMock()

        await askq_callback(update, context)

        assert 0 in pq.selected
        assert not future.done()  # Not resolved yet, waiting for Done
        query.edit_message_reply_markup.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_select_done(self):
        """Done button resolves multi-select with selected labels."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick many?",
            options=[{"label": "A", "description": ""}, {"label": "B", "description": ""}],
            multi_select=True,
            selected={0, 1},
            message_id=42,
        )
        register_pending(200, 100, pq)

        query = AsyncMock()
        query.data = "askq:0:done"
        query.from_user.id = 200
        query.message.chat_id = 100
        query.message.message_id = 42
        query.message.message_thread_id = None

        update = MagicMock()
        update.callback_query = query

        context = MagicMock()

        await askq_callback(update, context)

        assert future.result() == "A, B"

    @pytest.mark.asyncio
    async def test_other_sets_awaiting_text(self):
        """Other button sets pq.awaiting_other and edits message."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick?",
            options=[{"label": "A", "description": ""}],
            multi_select=False,
            selected=set(),
            message_id=42,
        )
        register_pending(200, 100, pq)

        query = AsyncMock()
        query.data = "askq:0:other"
        query.from_user.id = 200
        query.message.chat_id = 100
        query.message.message_id = 42
        query.message.message_thread_id = None

        update = MagicMock()
        update.callback_query = query

        context = MagicMock()

        await askq_callback(update, context)

        assert pq.awaiting_other is True
        query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_expired_question(self):
        """Tapping a button with no pending question shows expired message."""
        query = AsyncMock()
        query.data = "askq:0:0"
        query.from_user.id = 200
        query.message.chat_id = 100
        query.message.message_id = 42
        query.message.message_thread_id = None

        update = MagicMock()
        update.callback_query = query

        context = MagicMock()

        await askq_callback(update, context)

        query.answer.assert_called_once_with(text="Question expired.", show_alert=True)


class TestAskqOtherText:
    @pytest.mark.asyncio
    async def test_captures_text_and_resolves(self):
        """Free-text reply resolves the pending question."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        pq = PendingQuestion(
            future=future,
            question_text="Pick?",
            options=[],
            multi_select=False,
            selected=set(),
            message_id=42,
        )
        pq.awaiting_other = True
        register_pending(200, 100, pq)

        message = MagicMock()
        message.text = "My custom answer"
        message.from_user.id = 200
        message.chat_id = 100

        update = MagicMock()
        update.message = message

        context = MagicMock()

        result = await askq_other_text(update, context)

        assert future.result() == "My custom answer"

    @pytest.mark.asyncio
    async def test_ignores_when_not_awaiting(self):
        """Text messages pass through when no Other is pending."""
        message = MagicMock()
        message.text = "regular message"
        message.from_user.id = 200
        message.chat_id = 100

        update = MagicMock()
        update.message = message

        context = MagicMock()

        result = await askq_other_text(update, context)

        # Should return None to let other handlers process it
        assert result is None
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_bot/test_interactive_questions.py::TestAskqCallback -v`
Expected: ImportError for `askq_callback`

**Step 3: Implement callback handlers**

Add to `src/bot/features/interactive_questions.py`. First, add `awaiting_other` field to `PendingQuestion`:

Update the `PendingQuestion` dataclass:
```python
@dataclass
class PendingQuestion:
    """A question waiting for user response."""

    future: asyncio.Future
    question_text: str
    options: List[Dict[str, Any]]
    multi_select: bool
    selected: Set[int]
    message_id: Optional[int]
    awaiting_other: bool = False
```

Then add the handlers:

```python
async def askq_callback(update: Any, context: Any) -> None:
    """Handle inline keyboard button taps for askq: callbacks."""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data  # e.g. "askq:0:1", "askq:0:t1", "askq:0:done", "askq:0:other"

    pq = get_pending(user_id, chat_id)
    if not pq:
        await query.answer(text="Question expired.", show_alert=True)
        return

    # Parse callback data: askq:<q_idx>:<action>
    parts = data.split(":")
    if len(parts) < 3:
        await query.answer(text="Invalid.", show_alert=True)
        return

    action = parts[2]

    if action == "other":
        # Switch to free-text input mode
        pq.awaiting_other = True
        await query.answer()
        await query.edit_message_text(
            text=f"**{pq.question_text}**\n\nType your answer:"
        )
        return

    if action == "done":
        # Multi-select done — resolve with selected labels
        selected_labels = [
            pq.options[i].get("label", f"Option {i}")
            for i in sorted(pq.selected)
            if i < len(pq.options)
        ]
        answer = ", ".join(selected_labels) if selected_labels else ""
        await query.answer()
        await query.edit_message_text(
            text=f"**{pq.question_text}**\n\n✓ {answer}"
        )
        resolve_pending(user_id, chat_id, answer)
        return

    if action.startswith("t"):
        # Multi-select toggle
        try:
            opt_idx = int(action[1:])
        except ValueError:
            await query.answer(text="Invalid.", show_alert=True)
            return

        if opt_idx in pq.selected:
            pq.selected.discard(opt_idx)
        else:
            pq.selected.add(opt_idx)

        # Rebuild keyboard with updated state
        q_idx = int(parts[1])
        keyboard = build_multi_select_keyboard(pq.options, q_idx, pq.selected)
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    # Single select — action is the option index
    try:
        opt_idx = int(action)
    except ValueError:
        await query.answer(text="Invalid.", show_alert=True)
        return

    if opt_idx < len(pq.options):
        label = pq.options[opt_idx].get("label", f"Option {opt_idx}")
    else:
        label = f"Option {opt_idx}"

    await query.answer()
    await query.edit_message_text(
        text=f"**{pq.question_text}**\n\n✓ {label}"
    )
    resolve_pending(user_id, chat_id, label)


async def askq_other_text(update: Any, context: Any) -> Optional[bool]:
    """Handle free-text replies for 'Other...' answers.

    This is registered as a MessageHandler with a low group number so it
    runs before the main agentic_text handler. Returns None to pass through
    if not handling an 'Other' response.
    """
    message = update.message
    if not message or not message.text:
        return None

    user_id = message.from_user.id
    chat_id = message.chat_id

    pq = get_pending(user_id, chat_id)
    if not pq or not pq.awaiting_other:
        return None  # Not our message, let other handlers process it

    # Capture the text and resolve
    answer = message.text.strip()
    pq.awaiting_other = False
    resolve_pending(user_id, chat_id, answer)
    return True  # Consumed the message
```

**Step 4: Run tests**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_bot/test_interactive_questions.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/bot/features/interactive_questions.py tests/unit/test_bot/test_interactive_questions.py
git commit -m "feat: add Telegram callback and text handlers for interactive questions"
```

---

### Task 4: Wire the hook into sdk_integration.py

**Files:**
- Modify: `src/claude/sdk_integration.py` (lines 243-300)
- Modify: `src/claude/facade.py` (lines 40-176)
- Test: `tests/unit/test_claude/test_sdk_integration.py`

**Step 1: Write failing tests**

Add to `tests/unit/test_claude/test_sdk_integration.py`:

```python
from src.bot.features.interactive_questions import TelegramContext


class TestExecuteCommandHooks:
    @pytest.mark.asyncio
    async def test_hooks_set_when_telegram_context_provided(self):
        """Verify PreToolUse hook is registered when telegram_context is passed."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.claude.sdk_integration import ClaudeSDKManager
        from src.config.settings import Settings

        settings = MagicMock(spec=Settings)
        settings.claude_max_turns = 10
        settings.claude_max_cost_per_request = 1.0
        settings.claude_allowed_tools = []
        settings.claude_disallowed_tools = []
        settings.claude_cli_path = None
        settings.sandbox_enabled = False
        settings.sandbox_excluded_commands = []
        settings.enable_mcp = False
        settings.mcp_config_path = None
        settings.claude_timeout_seconds = 60

        manager = ClaudeSDKManager(settings)

        tg_ctx = TelegramContext(
            bot=AsyncMock(), chat_id=100, thread_id=5, user_id=200
        )

        # We can't fully run execute_command without a real CLI,
        # but we can verify the options are built correctly by
        # patching ClaudeSDKClient
        captured_options = {}
        with patch("src.claude.sdk_integration.ClaudeSDKClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client._query = AsyncMock()
            mock_client._query.receive_messages = AsyncMock(return_value=AsyncMock())
            mock_client_cls.return_value = mock_client

            # Make it raise early so we can inspect options
            mock_client.connect.side_effect = Exception("test stop")

            try:
                await manager.execute_command(
                    prompt="test",
                    working_directory=Path("/tmp"),
                    telegram_context=tg_ctx,
                )
            except Exception:
                pass

            # Check that hooks were set on the options
            call_args = mock_client_cls.call_args
            options = call_args[0][0] if call_args[0] else call_args[1].get("options")
            assert options.hooks is not None
            assert "PreToolUse" in options.hooks
            matchers = options.hooks["PreToolUse"]
            assert len(matchers) == 1
            assert matchers[0].matcher == "AskUserQuestion"

    @pytest.mark.asyncio
    async def test_no_hooks_without_telegram_context(self):
        """Verify no hooks set when telegram_context is None."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.claude.sdk_integration import ClaudeSDKManager
        from src.config.settings import Settings

        settings = MagicMock(spec=Settings)
        settings.claude_max_turns = 10
        settings.claude_max_cost_per_request = 1.0
        settings.claude_allowed_tools = []
        settings.claude_disallowed_tools = []
        settings.claude_cli_path = None
        settings.sandbox_enabled = False
        settings.sandbox_excluded_commands = []
        settings.enable_mcp = False
        settings.mcp_config_path = None
        settings.claude_timeout_seconds = 60

        manager = ClaudeSDKManager(settings)

        captured_options = {}
        with patch("src.claude.sdk_integration.ClaudeSDKClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.connect.side_effect = Exception("test stop")
            mock_client_cls.return_value = mock_client

            try:
                await manager.execute_command(
                    prompt="test",
                    working_directory=Path("/tmp"),
                )
            except Exception:
                pass

            call_args = mock_client_cls.call_args
            options = call_args[0][0] if call_args[0] else call_args[1].get("options")
            assert not options.hooks  # Empty or None
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_claude/test_sdk_integration.py::TestExecuteCommandHooks -v`
Expected: TypeError — `execute_command()` doesn't accept `telegram_context`

**Step 3: Modify sdk_integration.py**

Add import at top of file (after line 30):

```python
from src.bot.features.interactive_questions import (
    TelegramContext,
    cancel_pending,
    make_ask_user_hook,
)
```

Also import `HookMatcher` from the SDK (add to the existing import block):

```python
from claude_agent_sdk import (
    ...existing imports...
    HookMatcher,
)
```

Modify `execute_command` signature (line 243):

```python
async def execute_command(
    self,
    prompt: str,
    working_directory: Path,
    session_id: Optional[str] = None,
    continue_session: bool = False,
    stream_callback: Optional[Callable[[StreamUpdate], None]] = None,
    call_id: Optional[int] = None,
    telegram_context: Optional["TelegramContext"] = None,
) -> ClaudeResponse:
```

After the `can_use_tool` block (after line 332), add:

```python
            # Register PreToolUse hook for AskUserQuestion if we have
            # Telegram context to send questions to
            if telegram_context:
                ask_hook = make_ask_user_hook(telegram_context)
                options.hooks = {
                    "PreToolUse": [
                        HookMatcher(
                            matcher="AskUserQuestion",
                            hooks=[ask_hook],
                        )
                    ]
                }
                logger.info("AskUserQuestion hook registered for Telegram")
```

In the `finally` block (around line 395-398), add cleanup:

```python
                finally:
                    if call_id is not None:
                        self._active_pids.pop(call_id, None)
                    # Cancel any pending questions on session end
                    if telegram_context:
                        cancel_pending(
                            telegram_context.user_id,
                            telegram_context.chat_id,
                        )
                    await client.disconnect()
```

**Step 4: Run tests**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_claude/test_sdk_integration.py::TestExecuteCommandHooks -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/claude/sdk_integration.py tests/unit/test_claude/test_sdk_integration.py
git commit -m "feat: wire PreToolUse hook for AskUserQuestion into SDK session options"
```

---

### Task 5: Thread telegram_context through facade.py

**Files:**
- Modify: `src/claude/facade.py` (lines 40-176)

**Step 1: Modify run_command signature**

```python
async def run_command(
    self,
    prompt: str,
    working_directory: Path,
    user_id: int,
    session_id: Optional[str] = None,
    on_stream: Optional[Callable[[StreamUpdate], None]] = None,
    force_new: bool = False,
    call_id: Optional[int] = None,
    telegram_context: Optional[Any] = None,
) -> ClaudeResponse:
```

**Step 2: Modify _execute signature and passthrough**

```python
async def _execute(
    self,
    prompt: str,
    working_directory: Path,
    session_id: Optional[str] = None,
    continue_session: bool = False,
    stream_callback: Optional[Callable] = None,
    call_id: Optional[int] = None,
    telegram_context: Optional[Any] = None,
) -> ClaudeResponse:
    """Execute command via SDK."""
    return await self.sdk_manager.execute_command(
        prompt=prompt,
        working_directory=working_directory,
        session_id=session_id,
        continue_session=continue_session,
        stream_callback=stream_callback,
        call_id=call_id,
        telegram_context=telegram_context,
    )
```

**Step 3: Pass telegram_context through all _execute calls in run_command**

In `run_command()`, update both `_execute` calls (lines 91-98 and 116-123):

```python
response = await self._execute(
    prompt=prompt,
    working_directory=working_directory,
    session_id=claude_session_id,
    continue_session=should_continue,
    stream_callback=on_stream,
    call_id=call_id,
    telegram_context=telegram_context,
)
```

And the retry call:

```python
response = await self._execute(
    prompt=prompt,
    working_directory=working_directory,
    session_id=None,
    continue_session=False,
    stream_callback=on_stream,
    call_id=call_id,
    telegram_context=telegram_context,
)
```

**Step 4: Run existing facade tests to verify no regressions**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_claude/test_facade.py -v`
Expected: PASS (existing tests don't pass telegram_context, defaults to None)

**Step 5: Commit**

```bash
git add src/claude/facade.py
git commit -m "feat: thread telegram_context through facade run_command and _execute"
```

---

### Task 6: Wire orchestrator to pass telegram_context

**Files:**
- Modify: `src/bot/orchestrator.py` (lines 846-920 and 307-365)

**Step 1: Modify agentic_text to pass telegram_context**

In `agentic_text()`, after extracting `chat = update.message.chat` (line 867), build the context:

```python
from src.bot.features.interactive_questions import TelegramContext

# Build Telegram context for interactive questions
tg_ctx = TelegramContext(
    bot=context.bot,
    chat_id=update.message.chat_id,
    thread_id=getattr(update.message, "message_thread_id", None),
    user_id=user_id,
)
```

Then pass it to `run_command()` (around line 909):

```python
task = asyncio.create_task(
    claude_integration.run_command(
        prompt=message_text,
        working_directory=current_dir,
        user_id=user_id,
        session_id=session_id,
        on_stream=on_stream,
        force_new=force_new,
        call_id=call_id,
        telegram_context=tg_ctx,
    )
)
```

**Step 2: Register askq callback handler**

In `_register_agentic_handlers()` (around line 351-365 where callback handlers are), add:

```python
from src.bot.features.interactive_questions import askq_callback, askq_other_text

# Interactive question handlers
app.add_handler(
    CallbackQueryHandler(askq_callback, pattern=r"^askq:"),
    group=0,  # Before menu callbacks
)

# "Other..." free-text capture — must run before agentic_text (group 10)
from telegram.ext import MessageHandler, filters
app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        askq_other_text,
    ),
    group=5,  # Between auth/rate-limit and agentic_text (group 10)
)
```

**Step 3: Run full test suite to verify no regressions**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS

**Step 4: Commit**

```bash
git add src/bot/orchestrator.py
git commit -m "feat: wire Telegram context and askq handlers into orchestrator"
```

---

### Task 7: Wire menu.py to pass telegram_context

**Files:**
- Modify: `src/bot/handlers/menu.py` (lines 434-446)

**Step 1: Build and pass telegram_context in INJECT_SKILL**

In the INJECT_SKILL section, before `run_command()` (around line 434):

```python
from src.bot.features.interactive_questions import TelegramContext

tg_ctx = TelegramContext(
    bot=context.bot,
    chat_id=chat_id,
    thread_id=thread_id,
    user_id=query.from_user.id,
)
```

Note: `thread_id` is already extracted at line 472 — move it earlier (before the `run_command` call).

Then pass to `run_command()`:

```python
response = await claude_integration.run_command(
    prompt=prompt,
    working_directory=current_dir,
    user_id=query.from_user.id,
    session_id=session_id,
    force_new=force_new,
    telegram_context=tg_ctx,
)
```

**Step 2: Run menu tests**

Run: `cd /home/florian/config/claude-code-telegram && python -m pytest tests/unit/test_bot/test_menu.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/bot/handlers/menu.py
git commit -m "feat: pass telegram_context from menu skill execution to Claude sessions"
```

---

### Task 8: Integration smoke test — deploy and test

**Step 1: Run full test suite**

```bash
cd /home/florian/config/claude-code-telegram && python -m pytest tests/ -v --timeout=30
```

Expected: All tests PASS

**Step 2: Lint**

```bash
cd /home/florian/config/claude-code-telegram && black src/bot/features/interactive_questions.py src/claude/sdk_integration.py src/claude/facade.py src/bot/orchestrator.py src/bot/handlers/menu.py
```

**Step 3: Copy to installed location**

```bash
cp src/bot/features/interactive_questions.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/bot/features/interactive_questions.py
cp src/claude/sdk_integration.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/claude/sdk_integration.py
cp src/claude/facade.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/claude/facade.py
cp src/bot/orchestrator.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/bot/orchestrator.py
cp src/bot/handlers/menu.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/bot/handlers/menu.py
```

**Step 4: Restart bot**

```bash
systemctl --user restart claude-telegram-bot
sleep 2
journalctl --user -u claude-telegram-bot.service --since "30 seconds ago" --no-pager | tail -20
```

Expected: Bot starts without errors, "AskUserQuestion hook registered" appears in logs on first interaction.

**Step 5: Test in Telegram**

1. Open /menu → pick a skill that uses AskUserQuestion (e.g. brainstorming from superpowers)
2. When Claude asks a question, verify inline buttons appear in Telegram
3. Tap a button, verify Claude receives the answer and continues
4. Test "Other..." flow: tap Other, type custom text, verify it's captured
5. Test multi-select if available

**Step 6: Commit and push**

```bash
git add -A
git commit -m "chore: lint and integration test pass"
git push origin feat/stop-command
```
