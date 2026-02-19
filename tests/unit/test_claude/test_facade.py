"""Test ClaudeIntegration facade — force_new skips auto-resume."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.claude.facade import ClaudeIntegration
from src.claude.session import ClaudeSession, InMemorySessionStorage, SessionManager
from src.config.settings import Settings


@pytest.fixture
def config(tmp_path):
    """Create test config."""
    return Settings(
        telegram_bot_token="test:token",
        telegram_bot_username="testbot",
        approved_directory=tmp_path,
        session_timeout_hours=24,
        max_sessions_per_user=5,
        use_sdk=False,
    )


@pytest.fixture
def session_manager(config):
    """Create session manager with in-memory storage."""
    storage = InMemorySessionStorage()
    return SessionManager(config, storage)


@pytest.fixture
def facade(config, session_manager):
    """Create facade with mocked process manager and tool monitor."""
    process_manager = MagicMock()
    tool_monitor = MagicMock()
    tool_monitor.validate_tool_call = AsyncMock(return_value=(True, None))
    tool_monitor.get_tool_stats = MagicMock(return_value={})
    tool_monitor.get_user_tool_usage = MagicMock(return_value={})

    integration = ClaudeIntegration(
        config=config,
        process_manager=process_manager,
        sdk_manager=None,
        session_manager=session_manager,
        tool_monitor=tool_monitor,
    )
    return integration


class TestForceNewSkipsAutoResume:
    """Verify that force_new=True prevents _find_resumable_session."""

    async def test_auto_resume_finds_existing_session(self, facade, session_manager):
        """Without force_new, run_command auto-resumes an existing session."""
        project = Path("/test/project")
        user_id = 123

        # Seed an existing non-temp session in storage
        existing = ClaudeSession(
            session_id="real-session-id",
            user_id=user_id,
            project_path=project,
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        await session_manager.storage.save_session(existing)
        session_manager.active_sessions[existing.session_id] = existing

        # _find_resumable_session should find it
        found = await facade._find_resumable_session(user_id, project)
        assert found is not None
        assert found.session_id == "real-session-id"

    async def test_force_new_skips_auto_resume(self, facade, session_manager):
        """With force_new=True, run_command does NOT auto-resume."""
        project = Path("/test/project")
        user_id = 123

        # Seed an existing non-temp session
        existing = ClaudeSession(
            session_id="real-session-id",
            user_id=user_id,
            project_path=project,
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        await session_manager.storage.save_session(existing)
        session_manager.active_sessions[existing.session_id] = existing

        # Mock _find_resumable_session to track whether it's called
        with patch.object(
            facade, "_find_resumable_session", wraps=facade._find_resumable_session
        ) as spy:
            # Mock _execute_with_fallback so we don't need a real Claude backend
            mock_response = MagicMock()
            mock_response.session_id = "new-session-id"
            mock_response.cost = 0.0
            mock_response.duration_ms = 100
            mock_response.num_turns = 1
            mock_response.tools_used = []
            mock_response.is_error = False
            mock_response.content = "ok"

            with patch.object(
                facade, "_execute_with_fallback", return_value=mock_response
            ):
                await facade.run_command(
                    prompt="hello",
                    working_directory=project,
                    user_id=user_id,
                    session_id=None,
                    force_new=True,
                )

            # _find_resumable_session should NOT have been called
            spy.assert_not_called()
