"""TaskReminderScheduler — checks for due/overdue tasks and sends notifications."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, List

import structlog

from ..events.types import AgentResponseEvent

if TYPE_CHECKING:
    from ..events.bus import EventBus
    from ..scheduler.scheduler import JobScheduler
    from ..storage.facade import Storage

logger = structlog.get_logger()

REMINDER_JOB_NAME = "task_reminders"
# Check every 30 minutes
REMINDER_CRON = "*/30 * * * *"

_REMINDER_PROMPT_PREFIX = "__TASK_REMINDERS__"


class TaskReminderScheduler:
    """Schedules periodic checks for due/overdue tasks and sends reminders."""

    def __init__(
        self,
        scheduler: "JobScheduler",
        storage: "Storage",
        event_bus: "EventBus",
        notification_chat_ids: List[int],
    ) -> None:
        self._scheduler = scheduler
        self._storage = storage
        self._event_bus = event_bus
        self._notification_chat_ids = notification_chat_ids

    async def start(self) -> None:
        """Register the periodic task reminder job."""
        # Check if already registered
        jobs = await self._scheduler.list_jobs()
        for job in jobs:
            if job.get("job_name") == REMINDER_JOB_NAME:
                logger.debug("Task reminder job already registered")
                return

        await self._scheduler.add_job(
            job_name=REMINDER_JOB_NAME,
            cron_expression=REMINDER_CRON,
            prompt=_REMINDER_PROMPT_PREFIX,
            target_chat_ids=self._notification_chat_ids,
        )
        logger.info("Task reminder scheduler started", cron=REMINDER_CRON)

    async def check_and_notify(self) -> None:
        """Check for due/overdue tasks and publish reminder notifications.

        Called directly by the event handler when it detects a
        __TASK_REMINDERS__ event, bypassing Claude.
        """
        # Get all users with profiles (we need to know who to check)
        all_profiles = await self._storage.profiles.list_all_profiles()

        now = datetime.now(UTC)
        today_str = now.strftime("%Y-%m-%d")
        hour = now.hour

        for profile in all_profiles:
            user_id = profile.user_id
            open_tasks = await self._storage.tasks.list_tasks(user_id, status="open")

            overdue: list[str] = []
            due_today: list[str] = []

            for task in open_tasks:
                if not task.due_date:
                    continue
                if task.due_date < today_str:
                    overdue.append(f"  - {task.title} (due {task.due_date})")
                elif task.due_date == today_str:
                    due_today.append(f"  - {task.title}")

            if not overdue and not due_today:
                continue

            # Only send overdue reminders during reasonable hours (8-22)
            if hour < 8 or hour > 22:
                continue

            lines = []
            if overdue:
                lines.append("<b>Overdue tasks:</b>")
                lines.extend(overdue)
            if due_today:
                lines.append("<b>Due today:</b>")
                lines.extend(due_today)

            message = "\n".join(lines)

            chat_id = profile.briefing_chat_id if profile.briefing_chat_id else 0

            await self._event_bus.publish(
                AgentResponseEvent(
                    chat_id=chat_id,
                    text=message,
                )
            )
            logger.info(
                "Sent task reminder",
                user_id=user_id,
                overdue=len(overdue),
                due_today=len(due_today),
            )
