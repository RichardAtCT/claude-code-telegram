"""BriefingAssembler — builds a daily personal briefing message."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ..storage.facade import Storage

logger = structlog.get_logger()


class BriefingAssembler:
    """Assembles the daily briefing from profile, memories, and tasks."""

    def __init__(self, storage: "Storage") -> None:
        self._storage = storage

    async def build(self, user_id: int) -> str:
        """Return a formatted daily briefing string."""
        profile = await self._storage.profiles.get_profile(user_id)
        memories = await self._storage.memories.list_memories(user_id)
        open_tasks = await self._storage.tasks.list_tasks(user_id, status="open")

        now = datetime.now(UTC)
        date_str = now.strftime("%A, %B %-d")

        name = (profile.name if profile else None) or "there"
        lines = [f"<b>Good morning, {name}!</b>  {date_str}\n"]

        # Tasks section
        if open_tasks:
            lines.append(f"<b>Open Tasks ({len(open_tasks)})</b>")
            for task in open_tasks[:10]:  # cap at 10
                due = f"  <i>due {task.due_date}</i>" if task.due_date else ""
                lines.append(f"  [{task.id}] {task.title}{due}")
            if len(open_tasks) > 10:
                lines.append(f"  ... and {len(open_tasks) - 10} more")
        else:
            lines.append("No open tasks — you're all clear!")

        # Memories / context reminders
        if memories:
            focus_memories = [m for m in memories if "focus" in m.key.lower() or "goal" in m.key.lower()]
            if focus_memories:
                lines.append("\n<b>Your Focus</b>")
                for mem in focus_memories:
                    lines.append(f"  {mem.value}")

        lines.append("\nHave a great day!")
        return "\n".join(lines)
