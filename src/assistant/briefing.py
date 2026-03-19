"""BriefingAssembler — builds a daily personal briefing prompt for Claude."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, List

import structlog

if TYPE_CHECKING:
    from ..storage.facade import Storage

logger = structlog.get_logger()


class BriefingAssembler:
    """Assembles context and a prompt so Claude can build a rich daily briefing.

    Instead of generating static HTML, this builds a prompt that Claude
    will process using its available MCP tools (Garmin, Calendar, Home Assistant).
    """

    def __init__(self, storage: "Storage") -> None:
        self._storage = storage

    async def build_prompt(self, user_id: int) -> str:
        """Return a Claude prompt that produces a personalised morning briefing."""
        profile = await self._storage.profiles.get_profile(user_id)
        memories = await self._storage.memories.list_memories(user_id)
        open_tasks = await self._storage.tasks.list_tasks(user_id, status="open")

        now = datetime.now(UTC)
        date_str = now.strftime("%A, %B %-d, %Y")
        name = (profile.name if profile else None) or "there"
        timezone = (profile.timezone if profile else None) or "UTC"

        # Build task context
        task_lines: List[str] = []
        overdue_lines: List[str] = []
        today_str = now.strftime("%Y-%m-%d")
        for task in open_tasks:
            due = f" (due {task.due_date})" if task.due_date else ""
            line = f"- {task.title}{due}"
            task_lines.append(line)
            if task.due_date and task.due_date <= today_str:
                overdue_lines.append(f"- {task.title} (due {task.due_date})")

        # Build memory context
        memory_lines = [f"- {m.key}: {m.value}" for m in memories]

        prompt_parts = [
            f"Generate a morning briefing for {name}. Today is {date_str}.",
            f"Their timezone is {timezone}.",
            "",
            "Include the following sections in your briefing:",
            "",
            "1. **Greeting** — warm, brief, mention the day/date",
            "",
        ]

        if overdue_lines:
            prompt_parts.extend(
                [
                    "2. **Overdue tasks** (IMPORTANT — highlight these):",
                    *overdue_lines,
                    "",
                ]
            )

        if task_lines:
            prompt_parts.extend(
                [
                    "3. **Open tasks:**",
                    *task_lines,
                    "",
                ]
            )
        else:
            prompt_parts.append("3. No open tasks — mention they're all clear.\n")

        if memory_lines:
            prompt_parts.extend(
                [
                    "Context about the user (use naturally, don't list):",
                    *memory_lines,
                    "",
                ]
            )

        prompt_parts.extend(
            [
                "4. **Health check** — Use Garmin MCP to get:",
                "   - Last night's sleep score and duration",
                "   - Current training readiness or body battery if available",
                "   - Yesterday's step count",
                "   Keep this brief (2-3 lines). If Garmin is unavailable, skip this section.",
                "",
                "5. **Today's schedule** — Use Google Calendar MCP to get today's events.",
                "   List upcoming events with times. If no calendar is available, skip.",
                "",
                "6. **Home status** — Use Home Assistant MCP to check:",
                "   - Current home temperature if available",
                "   - Any devices/lights left on that seem unusual",
                "   Keep very brief. If Home Assistant is unavailable, skip.",
                "",
                "Format the briefing as a clean, readable Telegram message (HTML formatting).",
                "Keep the entire briefing concise — aim for 15-25 lines max.",
                "Don't mention which tools you're using. Just present the information naturally.",
                "If an MCP tool fails or is unavailable, silently skip that section.",
            ]
        )

        return "\n".join(prompt_parts)

    async def build(self, user_id: int) -> str:
        """Return a static fallback briefing (used by /briefing now without Claude)."""
        profile = await self._storage.profiles.get_profile(user_id)
        open_tasks = await self._storage.tasks.list_tasks(user_id, status="open")
        memories = await self._storage.memories.list_memories(user_id)

        now = datetime.now(UTC)
        date_str = now.strftime("%A, %B %-d")

        name = (profile.name if profile else None) or "there"
        lines = [f"<b>Good morning, {name}!</b>  {date_str}\n"]

        if open_tasks:
            lines.append(f"<b>Open Tasks ({len(open_tasks)})</b>")
            for task in open_tasks[:10]:
                due = f"  <i>due {task.due_date}</i>" if task.due_date else ""
                lines.append(f"  [{task.id}] {task.title}{due}")
            if len(open_tasks) > 10:
                lines.append(f"  ... and {len(open_tasks) - 10} more")
        else:
            lines.append("No open tasks — you're all clear!")

        if memories:
            focus_memories = [
                m
                for m in memories
                if "focus" in m.key.lower() or "goal" in m.key.lower()
            ]
            if focus_memories:
                lines.append("\n<b>Your Focus</b>")
                for mem in focus_memories:
                    lines.append(f"  {mem.value}")

        lines.append("\nHave a great day!")
        return "\n".join(lines)
