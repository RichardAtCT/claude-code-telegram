"""ProactiveCheckin — periodic Claude-powered check for noteworthy events."""

from typing import TYPE_CHECKING, List

import structlog

if TYPE_CHECKING:
    from ..scheduler.scheduler import JobScheduler

logger = structlog.get_logger()

CHECKIN_JOB_NAME = "proactive_checkin"
# Run 3 times a day: 12:00, 17:00, 21:00
CHECKIN_CRON = "0 12,17,21 * * *"

CHECKIN_PROMPT = """\
You are doing a proactive check-in for the user. Check the following and ONLY \
respond if there is something genuinely noteworthy. If nothing interesting, \
respond with exactly "NOTHING_NOTABLE" and nothing else.

Things to check:

1. **Garmin activity** — Use Garmin MCP to check:
   - Any new activities completed today (runs, walks, workouts)
   - If they hit a personal record, congrats them enthusiastically
   - If they hit their step goal, mention it
   - If their body battery is very low or stress is very high, gently note it
   - Good sleep score (80+) deserves a mention

2. **Home Assistant** — Use Home Assistant MCP to check:
   - Any doors/windows left open for a long time
   - Lights on in empty rooms (if presence detection available)
   - Unusual temperature (too hot/cold)

Rules:
- Be brief (2-4 lines max)
- Be warm and encouraging, not clinical
- Don't repeat things you've already mentioned today
- If checking fails or tools aren't available, respond "NOTHING_NOTABLE"
- Only mention genuinely interesting things — don't force it
- Use HTML formatting for Telegram
"""


class ProactiveCheckinScheduler:
    """Schedules periodic proactive check-ins via Claude."""

    def __init__(
        self,
        scheduler: "JobScheduler",
        notification_chat_ids: List[int],
    ) -> None:
        self._scheduler = scheduler
        self._notification_chat_ids = notification_chat_ids

    async def start(self) -> None:
        """Register the proactive check-in job if not already registered."""
        jobs = await self._scheduler.list_jobs()
        for job in jobs:
            if job.get("job_name") == CHECKIN_JOB_NAME:
                logger.debug("Proactive check-in job already registered")
                return

        await self._scheduler.add_job(
            job_name=CHECKIN_JOB_NAME,
            cron_expression=CHECKIN_CRON,
            prompt=CHECKIN_PROMPT,
            target_chat_ids=self._notification_chat_ids,
        )
        logger.info("Proactive check-in scheduler started", cron=CHECKIN_CRON)
