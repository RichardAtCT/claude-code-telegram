"""Shared test fixtures for Claude module tests."""

from typing import Dict, List, Optional

import structlog

from src.claude.session import ClaudeSession, SessionStorage

logger = structlog.get_logger()


class InMemorySessionStorage(SessionStorage):
    """In-memory session storage for testing."""

    def __init__(self):
        self.sessions: Dict[str, ClaudeSession] = {}

    async def save_session(self, session: ClaudeSession) -> None:
        self.sessions[session.session_id] = session

    async def load_session(
        self, session_id: str, user_id: int
    ) -> Optional[ClaudeSession]:
        session = self.sessions.get(session_id)
        if session and session.user_id != user_id:
            logger.warning(
                "Session ownership mismatch",
                session_id=session_id,
                session_owner=session.user_id,
                requesting_user=user_id,
            )
            return None
        return session

    async def delete_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    async def get_user_sessions(self, user_id: int) -> List[ClaudeSession]:
        return [s for s in self.sessions.values() if s.user_id == user_id]

    async def get_all_sessions(self) -> List[ClaudeSession]:
        return list(self.sessions.values())
