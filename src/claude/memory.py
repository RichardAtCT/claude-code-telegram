"""Session memory service for cross-session context.

Summarizes ended sessions and injects context into new sessions.
"""

from typing import List, Optional

import structlog

from ..config.settings import Settings
from ..storage.facade import Storage
from ..storage.models import MessageModel
from .sdk_integration import ClaudeSDKManager

logger = structlog.get_logger()

_SUMMARIZATION_PROMPT = (
    "Summarize the following conversation between a user and an AI coding assistant. "
    "Focus on: (1) what the user was working on, (2) key decisions made, "
    "(3) problems encountered and how they were resolved, (4) current state of the work. "
    "Keep the summary concise (3-5 bullet points, max 500 words).\n\n"
    "Conversation:\n{transcript}"
)

_MAX_TRANSCRIPT_CHARS = 12000


class SessionMemoryService:
    """Manages session memory: summarization and retrieval."""

    def __init__(
        self,
        storage: Storage,
        sdk_manager: ClaudeSDKManager,
        config: Settings,
    ):
        self.storage = storage
        self.sdk_manager = sdk_manager
        self.config = config

    async def summarize_session(
        self,
        session_id: str,
        user_id: int,
        project_path: str,
    ) -> Optional[str]:
        """Summarize a session and store the memory."""
        messages = await self.storage.messages.get_session_messages(
            session_id, limit=50
        )

        if len(messages) < self.config.session_memory_min_messages:
            logger.info(
                "Session too short to summarize",
                session_id=session_id,
                message_count=len(messages),
            )
            return None

        transcript = self._build_transcript(messages)
        summary = await self._generate_summary(transcript)

        await self.storage.session_memories.save_memory(
            user_id=user_id,
            project_path=project_path,
            session_id=session_id,
            summary=summary,
        )

        await self.storage.session_memories.deactivate_old_memories(
            user_id=user_id,
            project_path=project_path,
            keep_count=self.config.session_memory_max_count,
        )

        logger.info(
            "Session memory saved",
            session_id=session_id,
            summary_length=len(summary),
        )
        return summary

    async def get_memory_context(
        self,
        user_id: int,
        project_path: str,
    ) -> Optional[str]:
        """Retrieve stored memories formatted for system prompt injection."""
        memories = await self.storage.session_memories.get_active_memories(
            user_id=user_id,
            project_path=project_path,
            limit=self.config.session_memory_max_count,
        )

        if not memories:
            return None

        header = (
            "## Previous Session Context\n"
            "Summaries from previous sessions with this user:\n"
        )
        sections = []
        for mem in memories:
            ts = mem.created_at.isoformat() if mem.created_at else "unknown"
            sections.append(f"- [{ts}] {mem.summary}")

        context = header + "\n".join(sections)

        # Cap total length to avoid bloating system prompt
        if len(context) > 2000:
            context = context[:2000] + "\n... (truncated)"

        return context

    def _build_transcript(self, messages: List[MessageModel]) -> str:
        """Build a condensed transcript from messages."""
        # Messages come newest-first from DB, reverse for chronological order
        messages = list(reversed(messages))
        parts = []
        total_len = 0

        for msg in messages:
            line = f"User: {msg.prompt}"
            if msg.response:
                # Truncate long responses
                resp = (
                    msg.response[:500] + "..."
                    if len(msg.response) > 500
                    else msg.response
                )
                line += f"\nAssistant: {resp}"

            if total_len + len(line) > _MAX_TRANSCRIPT_CHARS:
                break
            parts.append(line)
            total_len += len(line)

        return "\n\n".join(parts)

    async def _generate_summary(self, transcript: str) -> str:
        """Call Claude to generate a summary of the conversation."""
        from pathlib import Path

        prompt = _SUMMARIZATION_PROMPT.format(transcript=transcript)

        response = await self.sdk_manager.execute_command(
            prompt=prompt,
            working_directory=Path(self.config.approved_directory),
            session_id=None,
            continue_session=False,
        )
        return response.content
