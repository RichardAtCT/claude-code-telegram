"""Interactive question routing for AskUserQuestion tool calls."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

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
    selected: Set[int] = field(default_factory=set)
    message_id: Optional[int] = None
    awaiting_other: bool = False


# Module-level registry: (user_id, chat_id) -> PendingQuestion
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
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="Other...", callback_data=f"askq:{question_idx}:other"
            )
        ]
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
        [
            InlineKeyboardButton(
                text="Other...", callback_data=f"askq:{question_idx}:other"
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="Done ✓", callback_data=f"askq:{question_idx}:done")]
    )
    return InlineKeyboardMarkup(rows)


def make_ask_user_hook(
    tg_ctx: TelegramContext,
) -> Callable[..., Any]:
    """Return an async PreToolUse hook callback that intercepts AskUserQuestion.

    The hook sends inline keyboards to the Telegram chat and awaits
    the user's selection before returning the answers back to Claude.
    """

    async def hook(
        input_data: Dict[str, Any],
        tool_use_id: Optional[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        if tool_name != "AskUserQuestion":
            return {}

        tool_input: Dict[str, Any] = input_data.get("tool_input", {})
        questions: List[Dict[str, Any]] = tool_input.get("questions", [])
        answers: Dict[str, str] = {}

        for q_idx, question in enumerate(questions):
            q_text = question.get("question", "")
            options: List[Dict[str, Any]] = question.get("options", [])
            multi_select: bool = question.get("multiSelect", False)

            if multi_select:
                keyboard = build_multi_select_keyboard(options, q_idx, set())
            else:
                keyboard = build_single_select_keyboard(options, q_idx)

            loop = asyncio.get_running_loop()
            future: asyncio.Future[str] = loop.create_future()
            pq = PendingQuestion(
                future=future,
                question_text=q_text,
                options=options,
                multi_select=multi_select,
            )
            register_pending(tg_ctx.user_id, tg_ctx.chat_id, pq)

            text = format_question_text(q_text, options)
            try:
                kwargs: Dict[str, Any] = {
                    "chat_id": tg_ctx.chat_id,
                    "text": text,
                    "reply_markup": keyboard,
                    "parse_mode": "Markdown",
                }
                if tg_ctx.thread_id is not None:
                    kwargs["message_thread_id"] = tg_ctx.thread_id
                msg = await tg_ctx.bot.send_message(**kwargs)
                pq.message_id = msg.message_id
            except Exception:
                logger.exception("Failed to send question to Telegram")
                cancel_pending(tg_ctx.user_id, tg_ctx.chat_id)
                return {}

            try:
                answer = await future
            except asyncio.CancelledError:
                return {}

            answers[q_text] = answer

        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {**tool_input, "answers": answers},
            }
        }

    return hook


async def askq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callbacks for interactive questions (askq:* pattern)."""
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "askq":
        return

    _prefix, q_idx_str, action = parts
    q_idx = int(q_idx_str)  # noqa: F841 – kept for clarity / future use

    user_id = query.from_user.id if query.from_user else 0
    chat_id = query.message.chat.id if query.message else 0
    pq = get_pending(user_id, chat_id)

    if pq is None:
        await query.answer("Question expired.", show_alert=True)
        return

    # Single select: action is a digit
    if action.isdigit():
        idx = int(action)
        label = pq.options[idx].get("label", f"Option {idx}")
        resolve_pending(user_id, chat_id, label)
        await query.answer()
        await query.edit_message_text(f"✓ {label}")
        return

    # Multi-select toggle: action starts with "t"
    if action.startswith("t") and action[1:].isdigit():
        idx = int(action[1:])
        if idx in pq.selected:
            pq.selected.discard(idx)
        else:
            pq.selected.add(idx)
        keyboard = build_multi_select_keyboard(pq.options, q_idx, pq.selected)
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    # Multi-select done
    if action == "done":
        labels = [
            pq.options[i].get("label", f"Option {i}") for i in sorted(pq.selected)
        ]
        answer = ", ".join(labels)
        resolve_pending(user_id, chat_id, answer)
        await query.answer()
        await query.edit_message_text(f"✓ {answer}")
        return

    # Other: free-text input requested
    if action == "other":
        pq.awaiting_other = True
        await query.answer()
        await query.edit_message_text("Type your answer:")
        return


async def askq_other_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-text replies for the 'Other...' option.

    Raises ``ApplicationHandlerStop`` if the message was consumed (pending
    question resolved), which prevents further handler groups (e.g. the
    agentic_text handler at group 10) from processing this message.
    If no pending "Other" question exists, returns normally so the message
    falls through to the next handler group.
    """
    if update.message is None:
        return

    user_id = update.message.from_user.id if update.message.from_user else 0
    chat_id = update.message.chat.id

    pq = get_pending(user_id, chat_id)
    if pq is None or not pq.awaiting_other:
        return

    answer = update.message.text or ""
    resolve_pending(user_id, chat_id, answer)
    raise ApplicationHandlerStop()
