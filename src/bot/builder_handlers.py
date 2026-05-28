"""Telegram /builder commands for Dex Phase 2 Builder."""
from __future__ import annotations
import json, os
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes

def _data_dir() -> Path:
    return Path(os.environ.get("BUILDER_DATA_DIR", r"C:\Users\odral\data\builder"))

def _state() -> dict:
    p = _data_dir() / "state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"stage": "IDLE"}

async def handle_builder_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = _state()
    if s.get("stage", "IDLE") == "IDLE":
        await update.message.reply_text("Builder idle. No ticket in flight.")
        return
    await update.message.reply_text(
        f"Builder: {s.get('ticket_id')} at {s['stage']} "
        f"(tick {s.get('ticks_used',0)}/10, attempts {s.get('implement_attempts',0)})")

async def handle_builder_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /builder kill <id>"); return
    p = _data_dir() / "state.json"
    s = _state(); s["kill_requested"] = context.args[0]
    p.write_text(json.dumps(s, indent=2), encoding="utf-8")
    await update.message.reply_text(f"Kill requested for {context.args[0]}. Builder stops at next tick; branch preserved.")

async def handle_builder_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = sorted((_data_dir() / "queue").glob("*.md"))
    inflight = _state().get("ticket_id")
    lines = [f"In flight: {inflight or 'none'}"] + [f"Queued: {p.stem}" for p in q]
    await update.message.reply_text("\n".join(lines) if lines else "Queue empty.")

async def handle_builder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Router for `/builder <sub>` — sub = status (default) | kill <id> | queue."""
    sub = (context.args[0].lower() if context.args else "status")
    if sub == "kill":
        context.args = context.args[1:]
        return await handle_builder_kill(update, context)
    if sub == "queue":
        return await handle_builder_queue(update, context)
    return await handle_builder_status(update, context)
