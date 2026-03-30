"""Schedule command handler for managing scheduled jobs via Telegram."""

from typing import List

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from ...scheduler.scheduler import JobScheduler
from ..utils.html_format import escape_html

logger = structlog.get_logger()


def _get_scheduler(context: ContextTypes.DEFAULT_TYPE) -> JobScheduler | None:
    """Get the JobScheduler from bot dependencies."""
    return context.bot_data.get("scheduler")


async def schedule_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /schedule command with subcommands.

    Usage:
        /schedule list
        /schedule add <name> <cron_expr> <prompt>
        /schedule remove <job_id>
        /schedule pause <job_id>
        /schedule resume <job_id>
    """
    scheduler = _get_scheduler(context)
    if not scheduler:
        await update.message.reply_text(
            "Scheduler is not enabled. Set ENABLE_SCHEDULER=true to use this command."
        )
        return

    args: List[str] = context.args or []

    if not args:
        await _show_usage(update)
        return

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "list":
        await _handle_list(update, scheduler)
    elif subcommand == "add":
        await _handle_add(update, context, scheduler, sub_args)
    elif subcommand == "remove":
        await _handle_remove(update, scheduler, sub_args)
    elif subcommand == "pause":
        await _handle_pause(update, scheduler, sub_args)
    elif subcommand == "resume":
        await _handle_resume(update, scheduler, sub_args)
    else:
        await _show_usage(update)


async def _show_usage(update: Update) -> None:
    """Show usage information."""
    await update.message.reply_html(
        "<b>Usage:</b>\n"
        "/schedule list\n"
        "/schedule add &lt;name&gt; &lt;cron&gt; &lt;prompt&gt;\n"
        "/schedule remove &lt;job_id&gt;\n"
        "/schedule pause &lt;job_id&gt;\n"
        "/schedule resume &lt;job_id&gt;\n\n"
        "<b>Cron format:</b> min hour day month weekday\n"
        "Example: <code>/schedule add daily-report 0 9 * * * Check status</code>"
    )


async def _handle_list(update: Update, scheduler: JobScheduler) -> None:
    """List all scheduled jobs."""
    jobs = await scheduler.list_jobs(include_paused=True)

    if not jobs:
        await update.message.reply_text("No scheduled jobs.")
        return

    lines = ["<b>Scheduled Jobs:</b>\n"]
    for job in jobs:
        status = "active" if job.get("is_active") else "paused"
        name = escape_html(job.get("job_name", "?"))
        cron = escape_html(job.get("cron_expression", "?"))
        job_id = escape_html(str(job.get("job_id", "?")))
        lines.append(
            f"<b>{name}</b> [{status}]\n"
            f"  Cron: <code>{cron}</code>\n"
            f"  ID: <code>{job_id}</code>"
        )

    await update.message.reply_html("\n\n".join(lines))


async def _handle_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    scheduler: JobScheduler,
    args: List[str],
) -> None:
    """Add a new scheduled job.

    Expected args: <name> <min> <hour> <day> <month> <weekday> <prompt...>
    The 5 cron fields are joined into a single cron expression.
    """
    # Need at least: name + 5 cron fields + 1 prompt word = 7
    if len(args) < 7:
        await update.message.reply_html(
            "<b>Usage:</b> /schedule add &lt;name&gt; "
            "&lt;min&gt; &lt;hour&gt; &lt;day&gt; &lt;month&gt; &lt;weekday&gt; "
            "&lt;prompt&gt;\n\n"
            "Example: <code>/schedule add daily-report 0 9 * * * Check status</code>"
        )
        return

    job_name = args[0]
    cron_expression = " ".join(args[1:6])
    prompt = " ".join(args[6:])

    # Auto-populate fields from context
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    settings = context.bot_data.get("settings")
    working_dir = context.user_data.get(
        "current_directory",
        settings.approved_directory if settings else None,
    )

    try:
        job_id = await scheduler.add_job(
            job_name=job_name,
            cron_expression=cron_expression,
            prompt=prompt,
            target_chat_ids=[chat_id],
            working_directory=working_dir,
            created_by=user_id,
        )
        await update.message.reply_html(
            f"Job <b>{escape_html(job_name)}</b> created.\n"
            f"ID: <code>{escape_html(job_id)}</code>\n"
            f"Cron: <code>{escape_html(cron_expression)}</code>"
        )
    except Exception as e:
        logger.exception("Failed to add scheduled job", error=str(e))
        await update.message.reply_text(f"Failed to create job: {e}")


async def _handle_remove(
    update: Update, scheduler: JobScheduler, args: List[str]
) -> None:
    """Remove a scheduled job."""
    if not args:
        await update.message.reply_text("Usage: /schedule remove <job_id>")
        return

    job_id = args[0]
    await scheduler.remove_job(job_id)
    await update.message.reply_html(
        f"Job <code>{escape_html(job_id)}</code> removed."
    )


async def _handle_pause(
    update: Update, scheduler: JobScheduler, args: List[str]
) -> None:
    """Pause a scheduled job."""
    if not args:
        await update.message.reply_text("Usage: /schedule pause <job_id>")
        return

    job_id = args[0]
    success = await scheduler.pause_job(job_id)
    if success:
        await update.message.reply_html(
            f"Job <code>{escape_html(job_id)}</code> paused."
        )
    else:
        await update.message.reply_text(f"Job '{job_id}' not found.")


async def _handle_resume(
    update: Update, scheduler: JobScheduler, args: List[str]
) -> None:
    """Resume a paused job."""
    if not args:
        await update.message.reply_text("Usage: /schedule resume <job_id>")
        return

    job_id = args[0]
    success = await scheduler.resume_job(job_id)
    if success:
        await update.message.reply_html(
            f"Job <code>{escape_html(job_id)}</code> resumed."
        )
    else:
        await update.message.reply_text(f"Job '{job_id}' not found or failed to resume.")
