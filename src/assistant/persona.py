"""PersonaBuilder — assembles the Claude system prompt prefix from user profile + memories."""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ..storage.facade import Storage

logger = structlog.get_logger()

_STYLE_DESCRIPTIONS = {
    "concise": "Be brief and to the point.",
    "detailed": "Provide thorough explanations with context.",
    "friendly": "Use a warm, conversational tone.",
    "formal": "Use professional, precise language.",
}


class PersonaBuilder:
    """Builds a personalised system prompt prefix for a given user."""

    def __init__(self, storage: "Storage") -> None:
        self._storage = storage

    async def build(self, user_id: int) -> str:
        """Return the personalised system prompt prefix for user_id."""
        profile = await self._storage.profiles.get_profile(user_id)
        memories = await self._storage.memories.list_memories(user_id)

        lines = ["You are a personal AI assistant."]

        if profile and profile.name:
            lines.append(f"The user's name is {profile.name}.")

        if profile and profile.timezone and profile.timezone != "UTC":
            lines.append(f"The user's timezone is {profile.timezone}.")

        style = (profile.communication_style if profile else None) or "concise"
        style_desc = _STYLE_DESCRIPTIONS.get(style)
        if style_desc:
            lines.append(f"Communication style ({style}): {style_desc}")
        else:
            lines.append(f"Communication style: {style}")

        if memories:
            lines.append("\nThings to remember about the user:")
            for mem in memories:
                lines.append(f"- {mem.key}: {mem.value}")

        return "\n".join(lines)
