"""Job scheduler for recurring agent tasks.

Wraps APScheduler's AsyncIOScheduler and publishes ScheduledEvents
to the event bus when jobs fire.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from apscheduler.schedulers.asyncio import (
    AsyncIOScheduler,  # type: ignore[import-untyped]
)
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.date import DateTrigger  # type: ignore[import-untyped]

from ..events.bus import EventBus
from ..events.types import ScheduledEvent
from ..storage.database import DatabaseManager

_CHECKIN_POLL_SECONDS = 30

logger = structlog.get_logger()


class JobScheduler:
    """Cron scheduler that publishes ScheduledEvents to the event bus."""

    def __init__(
        self,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        default_working_directory: Path,
    ) -> None:
        self.event_bus = event_bus
        self.db_manager = db_manager
        self.default_working_directory = default_working_directory
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        """Load persisted jobs and start the scheduler."""
        await self._load_jobs_from_db()
        self._scheduler.start()

        # Poll for new check-ins created by the CLI
        self._scheduler.add_job(
            self._poll_new_checkins,
            "interval",
            seconds=_CHECKIN_POLL_SECONDS,
            id="_checkin_poller",
            replace_existing=True,
        )
        logger.info("Job scheduler started")

    async def stop(self) -> None:
        """Shutdown the scheduler gracefully."""
        self._scheduler.shutdown(wait=False)
        logger.info("Job scheduler stopped")

    async def add_job(
        self,
        job_name: str,
        cron_expression: str,
        prompt: str,
        target_chat_ids: Optional[List[int]] = None,
        working_directory: Optional[Path] = None,
        skill_name: Optional[str] = None,
        created_by: int = 0,
    ) -> str:
        """Add a new scheduled job.

        Args:
            job_name: Human-readable job name.
            cron_expression: Cron-style schedule (e.g. "0 9 * * 1-5").
            prompt: The prompt to send to Claude when the job fires.
            target_chat_ids: Telegram chat IDs to send the response to.
            working_directory: Working directory for Claude execution.
            skill_name: Optional skill to invoke.
            created_by: Telegram user ID of the creator.

        Returns:
            The job ID.
        """
        trigger = CronTrigger.from_crontab(cron_expression)
        work_dir = working_directory or self.default_working_directory

        job = self._scheduler.add_job(
            self._fire_event,
            trigger=trigger,
            kwargs={
                "job_name": job_name,
                "prompt": prompt,
                "working_directory": str(work_dir),
                "target_chat_ids": target_chat_ids or [],
                "skill_name": skill_name,
            },
            name=job_name,
        )

        # Persist to database
        await self._save_job(
            job_id=job.id,
            job_name=job_name,
            cron_expression=cron_expression,
            prompt=prompt,
            target_chat_ids=target_chat_ids or [],
            working_directory=str(work_dir),
            skill_name=skill_name,
            created_by=created_by,
        )

        logger.info(
            "Scheduled job added",
            job_id=job.id,
            job_name=job_name,
            cron=cron_expression,
        )
        return str(job.id)

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            logger.warning("Job not found in scheduler", job_id=job_id)

        await self._delete_job(job_id)
        logger.info("Scheduled job removed", job_id=job_id)
        return True

    async def list_jobs(self) -> List[Dict[str, Any]]:
        """List all scheduled jobs from the database."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM scheduled_jobs WHERE is_active = 1 ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def _fire_event(
        self,
        job_name: str,
        prompt: str,
        working_directory: str,
        target_chat_ids: List[int],
        skill_name: Optional[str],
    ) -> None:
        """Called by APScheduler when a job triggers. Publishes a ScheduledEvent."""
        event = ScheduledEvent(
            job_name=job_name,
            prompt=prompt,
            working_directory=Path(working_directory),
            target_chat_ids=target_chat_ids,
            skill_name=skill_name,
        )

        logger.info(
            "Scheduled job fired",
            job_name=job_name,
            event_id=event.id,
        )

        await self.event_bus.publish(event)

    async def _load_jobs_from_db(self) -> None:
        """Load persisted jobs and re-register them with APScheduler."""
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM scheduled_jobs WHERE is_active = 1"
                )
                rows = list(await cursor.fetchall())

            for row in rows:
                row_dict = dict(row)
                try:
                    trigger = CronTrigger.from_crontab(row_dict["cron_expression"])

                    # Parse target_chat_ids from stored string
                    chat_ids_str = row_dict.get("target_chat_ids", "")
                    chat_ids = (
                        [int(x) for x in chat_ids_str.split(",") if x.strip()]
                        if chat_ids_str
                        else []
                    )

                    self._scheduler.add_job(
                        self._fire_event,
                        trigger=trigger,
                        kwargs={
                            "job_name": row_dict["job_name"],
                            "prompt": row_dict["prompt"],
                            "working_directory": row_dict["working_directory"],
                            "target_chat_ids": chat_ids,
                            "skill_name": row_dict.get("skill_name"),
                        },
                        id=row_dict["job_id"],
                        name=row_dict["job_name"],
                        replace_existing=True,
                    )
                    logger.debug(
                        "Loaded scheduled job from DB",
                        job_id=row_dict["job_id"],
                        job_name=row_dict["job_name"],
                    )
                except Exception:
                    logger.exception(
                        "Failed to load scheduled job",
                        job_id=row_dict.get("job_id"),
                    )

            logger.info("Loaded scheduled jobs from database", count=len(rows))
        except Exception:
            # Table might not exist yet on first run
            logger.debug("No scheduled_jobs table found, starting fresh")

    async def _save_job(
        self,
        job_id: str,
        job_name: str,
        cron_expression: str,
        prompt: str,
        target_chat_ids: List[int],
        working_directory: str,
        skill_name: Optional[str],
        created_by: int,
    ) -> None:
        """Persist a job definition to the database."""
        chat_ids_str = ",".join(str(cid) for cid in target_chat_ids)
        async with self.db_manager.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO scheduled_jobs
                (job_id, job_name, cron_expression, prompt, target_chat_ids,
                 working_directory, skill_name, created_by, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    job_id,
                    job_name,
                    cron_expression,
                    prompt,
                    chat_ids_str,
                    working_directory,
                    skill_name,
                    created_by,
                ),
            )
            await conn.commit()

    async def _delete_job(self, job_id: str) -> None:
        """Soft-delete a job from the database."""
        async with self.db_manager.get_connection() as conn:
            await conn.execute(
                "UPDATE scheduled_jobs SET is_active = 0 WHERE job_id = ?",
                (job_id,),
            )
            await conn.commit()

    # --- Check-in polling ---

    async def _poll_new_checkins(self) -> None:
        """Poll for pending check-ins without a job_id and schedule them."""
        try:
            from src.lockstep.db import (
                get_db,
                get_pending_checkins_without_job,
                mark_checkin_fired,
                mark_checkin_picked_up,
            )
        except ImportError:
            return  # goals module not installed yet

        try:
            conn = get_db()
            pending = get_pending_checkins_without_job(conn)

            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)

            for checkin in pending:
                fire_at_raw = checkin["fire_at"]
                if isinstance(fire_at_raw, str):
                    fire_at = datetime.fromisoformat(fire_at_raw)
                else:
                    fire_at = fire_at_raw

                if fire_at.tzinfo is None:
                    fire_at = fire_at.replace(tzinfo=timezone.utc)

                checkin_id: str = checkin["id"]

                if fire_at <= now:
                    # Past due — fire immediately
                    mark_checkin_fired(conn, checkin_id)
                    await self._fire_checkin_event(checkin)
                    logger.info(
                        "Fired past-due checkin",
                        checkin_id=checkin_id,
                    )
                else:
                    # Schedule for the future
                    trigger = DateTrigger(run_date=fire_at)
                    job = self._scheduler.add_job(
                        self._fire_checkin_callback,
                        trigger=trigger,
                        kwargs={"checkin": dict(checkin)},
                        name=f"checkin-{checkin_id}",
                    )
                    mark_checkin_picked_up(conn, checkin_id, job.id)
                    logger.info(
                        "Scheduled checkin",
                        checkin_id=checkin_id,
                        fire_at=str(fire_at),
                        job_id=job.id,
                    )

            conn.close()
        except Exception:
            logger.exception("Error polling for new check-ins")

    async def _fire_checkin_callback(self, checkin: Dict[str, Any]) -> None:
        """APScheduler callback when a check-in fires."""
        try:
            from src.lockstep.db import get_db, mark_checkin_fired

            conn = get_db()
            mark_checkin_fired(conn, checkin["id"])
            conn.close()
        except Exception:
            logger.exception(
                "Failed to mark checkin as fired", checkin_id=checkin.get("id")
            )

        await self._fire_checkin_event(checkin)

    async def _fire_checkin_event(self, checkin: Dict[str, Any]) -> None:
        """Publish a ScheduledEvent for a check-in."""
        context = checkin.get("context", "")
        prompt = self._build_checkin_prompt(context)

        chat_id = checkin.get("chat_id", 0)
        target_chat_ids = [chat_id] if chat_id else []

        event = ScheduledEvent(
            job_name=f"checkin-{checkin['id']}",
            prompt=prompt,
            working_directory=self.default_working_directory,
            target_chat_ids=target_chat_ids,
            user_id=checkin.get("user_id", 0),
            session_id=checkin.get("session_id"),
        )

        logger.info(
            "Check-in event fired",
            checkin_id=checkin["id"],
            event_id=event.id,
        )

        await self.event_bus.publish(event)

    @staticmethod
    def _build_checkin_prompt(context: str) -> str:
        """Build the prompt Claude receives when a check-in fires."""
        return (
            "A scheduled check-in has fired.\n\n"
            f"Context: {context}\n\n"
            "Before responding:\n"
            "1. Read profiles/user.md\n"
            "2. Check active goals: python -m src.lockstep.cli list\n"
            "3. Check recent outcomes: python -m src.lockstep.cli history --days 3\n\n"
            "Then deliver the check-in based on the context above. "
            "Keep it concise and Telegram-friendly. "
            "At the end, schedule the next appropriate check-in."
        )
