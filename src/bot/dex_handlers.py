"""Telegram command handlers for Dex's async decision queue.

Each command appends a ``## Resolution`` block to the matching
``pending_decisions/<id>.md`` file in John's Obsidian vault. Dex picks up
resolved files on its next scheduled tick.

The ``fire-now`` variant of ``/yes`` additionally shells out to ``claude -p``
to invoke the ``update_scheduled_task`` MCP tool so Dex fires within ~1 minute
instead of waiting for the next cron tick.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

CUSTOM_VERBS = {"revive", "archive", "fold", "delete", "pause", "resume"}


def _pending_dir() -> Path:
    """Return the directory holding pending-decision markdown files.

    Honours the ``DEX_PENDING_DIR`` env var for tests; falls back to the
    canonical vault path otherwise.
    """
    env = os.environ.get("DEX_PENDING_DIR")
    if env:
        return Path(env)
    return Path(
        r"C:\Users\odral\Documents\Obsidian\John Gallardo\pending_decisions"
    )


def _decision_path(decision_id: str) -> Path:
    return _pending_dir() / f"{decision_id}.md"


def _append_resolution(
    decision_id: str, status: str, fire_now: bool = False
) -> bool:
    """Append a ``## Resolution`` block to the decision file.

    Returns ``True`` on success, ``False`` if the file does not exist.
    """
    path = _decision_path(decision_id)
    if not path.exists():
        return False
    block = [
        "",
        "## Resolution",
        f"status: {status}",
        f"resolved-at: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    if fire_now:
        block.append("fire-now: true")
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(block) + "\n")
    return True


async def _fire_now_dex() -> None:
    """Fire Dex within ~1 min via the ``update_scheduled_task`` MCP tool.

    Spawns a one-shot ``claude -p`` process; we don't care about its output,
    only that it returns within a reasonable timeout.
    """
    claude_cli = shutil.which("claude") or r"C:\Users\odral\.local\bin\claude.exe"
    prompt = (
        "Use the update_scheduled_task tool to update the scheduled task "
        "named 'dex' so its next fire time is within the next minute. "
        "After updating, exit with no further output."
    )
    proc = await asyncio.create_subprocess_exec(
        claude_cli,
        "-p",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()


async def handle_yes(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle ``/yes <id> [/now]`` — mark a pending decision as resolved-yes."""
    if not context.args:
        await update.message.reply_text("Usage: /yes <id> [/now]")
        return
    decision_id = context.args[0]
    fire_now = (
        len(context.args) > 1 and context.args[1].lower() == "/now"
    )
    ok = _append_resolution(decision_id, "resolved-yes", fire_now=fire_now)
    if not ok:
        await update.message.reply_text(f"Decision {decision_id} not found.")
        return
    if fire_now:
        await _fire_now_dex()
    suffix = " (fire-now requested)" if fire_now else ""
    await update.message.reply_text(
        f"Resolved {decision_id} = yes{suffix}. Dex picks up next tick."
    )


async def handle_no(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle ``/no <id>`` — mark a pending decision as resolved-no."""
    if not context.args:
        await update.message.reply_text("Usage: /no <id>")
        return
    decision_id = context.args[0]
    ok = _append_resolution(decision_id, "resolved-no")
    if not ok:
        await update.message.reply_text(f"Decision {decision_id} not found.")
        return
    await update.message.reply_text(
        f"Resolved {decision_id} = no. Cooldown 7 days."
    )


async def handle_custom_verb(
    verb: str, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generic handler for project-lifecycle verbs (revive/archive/etc)."""
    if not context.args:
        await update.message.reply_text(f"Usage: /{verb} <id>")
        return
    decision_id = context.args[0]
    ok = _append_resolution(decision_id, f"resolved-{verb}")
    if not ok:
        await update.message.reply_text(f"Decision {decision_id} not found.")
        return
    await update.message.reply_text(
        f"Resolved {decision_id} = {verb}. Dex picks up next tick."
    )


def make_verb_handler(verb: str):
    """Build a CommandHandler-compatible coroutine bound to a specific verb."""

    async def _h(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_custom_verb(verb, update, context)

    _h.__name__ = f"handle_{verb}"
    return _h
