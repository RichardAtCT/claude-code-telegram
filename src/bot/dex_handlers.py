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

# Plain-English meaning + inverse-verb hint for every confirmation reply.
# Keys are the verb passed to ``_compose_echo``.
_VERB_INFO: dict[str, dict[str, str]] = {
    "yes_approval": {
        "meaning": "KEEP ACTIVE",
        "next": "Dex applies next tick.",
        "reverse": "/no <id> to snooze 7d · /pause <id> · /archive <id>",
    },
    "yes_dispatch": {
        "meaning": "DISPATCH (Writer/Coder/Researcher will run)",
        "next": "Dex applies next tick.",
        "reverse": "/no <id> to skip",
    },
    "yes_dispatch_now": {
        "meaning": "DISPATCH IMMEDIATELY (fires within 1 min)",
        "next": "Dex fires within 1 min.",
        "reverse": "/no <id> to skip (must reply before tick fires)",
    },
    "no": {
        "meaning": "SKIP (7-day cooldown)",
        "next": "Dex applies next tick.",
        "reverse": "/yes <id> to reverse",
    },
    "pause": {
        "meaning": "PAUSE (flip status to paused)",
        "next": "Dex applies next tick.",
        "reverse": "/yes <id> to keep active · /revive <id>",
    },
    "revive": {
        "meaning": "REVIVE (flip status to active)",
        "next": "Dex applies next tick.",
        "reverse": "/pause <id> to re-pause",
    },
    "archive": {
        "meaning": "ARCHIVE (move to 11 Archive/)",
        "next": "Dex applies next tick.",
        "reverse": "/yes <id> to keep active (cannot undo archive easily)",
    },
    "fold": {
        "meaning": "FOLD (inline + delete source file)",
        "next": "Dex applies next tick.",
        "reverse": "/no <id> to skip (cannot undo)",
    },
    "delete": {
        "meaning": "DELETE",
        "next": "Dex applies next tick.",
        "reverse": "/no <id> to skip (cannot undo)",
    },
    "resume": {
        "meaning": "RESUME (flip status to active)",
        "next": "Dex applies next tick.",
        "reverse": "/pause <id> to re-pause",
    },
}


def _read_decision_meta(path: Path) -> dict:
    """Parse the YAML frontmatter of a decision file.

    Simple line-by-line parser — no external deps. Returns a dict with at
    least ``project``, ``agent``, ``type``, and ``task`` keys if present.
    Missing fields are simply absent from the returned dict.
    """
    meta: dict[str, str] = {}
    if not path.exists():
        return meta
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return meta
    lines = text.splitlines()
    # Frontmatter must start at the very first line with ``---``.
    if not lines or lines[0].strip() != "---":
        return meta
    in_frontmatter = True
    body_lines: list[str] = []
    for line in lines[1:]:
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        else:
            body_lines.append(line)
    # Capture the first non-empty line under ``## Task`` for dispatch context.
    for idx, line in enumerate(body_lines):
        if line.strip().lower() == "## task":
            for follow in body_lines[idx + 1 :]:
                if follow.strip():
                    meta["task"] = follow.strip()[:80]
                    break
            break
    return meta


def _decision_context(meta: dict) -> str:
    """Return a short human label for the decision (project, or agent + task)."""
    dtype = (meta.get("type") or "").lower()
    if dtype == "dispatch":
        agent = meta.get("agent") or "<no context>"
        task = meta.get("task")
        if task:
            return f"{agent}: {task}"
        return agent
    project = meta.get("project")
    if project:
        return project
    return "<no context>"


def _compose_echo(
    verb: str, decision_id: str, meta: dict, fire_now: bool = False
) -> str:
    """Build the confirmation reply for a resolved decision.

    ``verb`` is the bare command verb (e.g. ``"yes"``, ``"no"``, ``"pause"``).
    For ``yes`` the dispatch vs approval branch (and ``/now`` variant) is
    chosen from ``meta`` and ``fire_now``.
    """
    if verb == "yes":
        dtype = (meta.get("type") or "").lower()
        if dtype == "dispatch":
            key = "yes_dispatch_now" if fire_now else "yes_dispatch"
        else:
            key = "yes_approval"
    else:
        key = verb
    info = _VERB_INFO.get(key)
    if info is None:
        # Defensive fallback — unknown verb, keep terse but still informative.
        return (
            f"{decision_id} {_decision_context(meta)} "
            f"→ {verb.upper()}. Dex applies next tick."
        )
    context_label = _decision_context(meta)
    reverse_hint = info["reverse"].replace("<id>", decision_id)
    return (
        f"{decision_id} {context_label} → {info['meaning']}. "
        f"{info['next']}\n"
        f"↩ If wrong: {reverse_hint}"
    )


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
    path = _decision_path(decision_id)
    meta = _read_decision_meta(path)
    ok = _append_resolution(decision_id, "resolved-yes", fire_now=fire_now)
    if not ok:
        await update.message.reply_text(f"Decision {decision_id} not found.")
        return
    if fire_now:
        await _fire_now_dex()
    await update.message.reply_text(
        _compose_echo("yes", decision_id, meta, fire_now=fire_now)
    )


async def handle_no(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle ``/no <id>`` — mark a pending decision as resolved-no."""
    if not context.args:
        await update.message.reply_text("Usage: /no <id>")
        return
    decision_id = context.args[0]
    path = _decision_path(decision_id)
    meta = _read_decision_meta(path)
    ok = _append_resolution(decision_id, "resolved-no")
    if not ok:
        await update.message.reply_text(f"Decision {decision_id} not found.")
        return
    await update.message.reply_text(
        _compose_echo("no", decision_id, meta)
    )


async def handle_custom_verb(
    verb: str, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generic handler for project-lifecycle verbs (revive/archive/etc)."""
    if not context.args:
        await update.message.reply_text(f"Usage: /{verb} <id>")
        return
    decision_id = context.args[0]
    path = _decision_path(decision_id)
    meta = _read_decision_meta(path)
    ok = _append_resolution(decision_id, f"resolved-{verb}")
    if not ok:
        await update.message.reply_text(f"Decision {decision_id} not found.")
        return
    await update.message.reply_text(
        _compose_echo(verb, decision_id, meta)
    )


def make_verb_handler(verb: str):
    """Build a CommandHandler-compatible coroutine bound to a specific verb."""

    async def _h(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_custom_verb(verb, update, context)

    _h.__name__ = f"handle_{verb}"
    return _h
