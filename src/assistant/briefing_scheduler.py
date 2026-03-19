"""BriefingScheduler — registers/removes the daily briefing cron job per user."""

from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from ..scheduler.scheduler import JobScheduler
    from ..storage.facade import Storage

logger = structlog.get_logger()

BRIEFING_JOB_PREFIX = "briefing_user_"


class BriefingScheduler:
    """Manages per-user daily briefing scheduled jobs."""

    def __init__(self, scheduler: "JobScheduler", storage: "Storage") -> None:
        self._scheduler = scheduler
        self._storage = storage

    async def enable(self, user_id: int, chat_id: int, cron: str = "0 8 * * *") -> None:
        """Schedule (or reschedule) the briefing for a user."""
        job_name = f"{BRIEFING_JOB_PREFIX}{user_id}"

        # Remove existing job if present
        await self.disable(user_id)

        await self._scheduler.add_job(
            job_name=job_name,
            cron_expression=cron,
            prompt=f"__BRIEFING__:{user_id}",
            target_chat_ids=[chat_id],
            created_by=user_id,
        )

        # Persist to profile
        profile = await self._storage.profiles.get_profile(user_id)
        if not profile:
            from ..storage.models import UserProfileModel

            profile = UserProfileModel(user_id=user_id)
        updated = UserProfileModel(
            user_id=profile.user_id,
            name=profile.name,
            timezone=profile.timezone,
            wake_time=profile.wake_time,
            communication_style=profile.communication_style,
            briefing_enabled=True,
            briefing_cron=cron,
            briefing_chat_id=chat_id,
        )
        await self._storage.profiles.upsert_profile(updated)
        logger.info("Briefing enabled", user_id=user_id, cron=cron)

    async def disable(self, user_id: int) -> None:
        """Remove the briefing job for a user."""
        jobs = await self._scheduler.list_jobs()
        job_name = f"{BRIEFING_JOB_PREFIX}{user_id}"
        for job in jobs:
            if job.get("job_name") == job_name:
                await self._scheduler.remove_job(job["job_id"])
                break
        logger.info("Briefing disabled", user_id=user_id)
