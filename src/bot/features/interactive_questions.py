"""Interactive question routing for AskUserQuestion tool calls."""

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
