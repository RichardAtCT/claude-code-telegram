"""Test Claude session management."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.claude.sdk_integration import ClaudeResponse
from src.claude.session import ClaudeSession, InMemorySessionStorage, SessionManager
from src.config.settings import Settings


class TestClaudeSession:
    """Test ClaudeSession class."""

    def test_session_creation(self):
        """Test session creation."""
        session = ClaudeSession(
            session_id="test-session",
            user_id=123,
            project_path=Path("/test/path"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )

        assert session.session_id == "test-session"
        assert session.user_id == 123
        assert session.project_path == Path("/test/path")
        assert session.total_cost == 0.0
        assert session.total_turns == 0
        assert session.message_count == 0
        assert session.tools_used == []

    def test_session_expiry(self):
        """Test session expiry logic."""
        now = datetime.now(UTC)
        old_time = now - timedelta(hours=25)

        session = ClaudeSession(
            session_id="test-session",
            user_id=123,
            project_path=Path("/test/path"),
            created_at=old_time,
            last_used=old_time,
        )

        # Should be expired after 24 hours
        assert session.is_expired(24) is True
        assert session.is_expired(48) is False

    def test_update_usage(self):
        """Test usage update."""
        session = ClaudeSession(
            session_id="test-session",
            user_id=123,
            project_path=Path("/test/path"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )

        response = ClaudeResponse(
            content="Test response",
            session_id="test-session",
            cost=0.05,
            duration_ms=1000,
            num_turns=2,
            tools_used=[{"name": "Read"}, {"name": "Write"}],
        )

        session.update_usage(response)

        assert session.total_cost == 0.05
        assert session.total_turns == 2
        assert session.message_count == 1
        assert "Read" in session.tools_used
        assert "Write" in session.tools_used

    def test_to_dict_and_from_dict(self):
        """Test serialization/deserialization."""
        original = ClaudeSession(
            session_id="test-session",
            user_id=123,
            project_path=Path("/test/path"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
            total_cost=0.05,
            total_turns=2,
            message_count=1,
            tools_used=["Read", "Write"],
        )

        # Convert to dict and back
        data = original.to_dict()
        restored = ClaudeSession.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.project_path == original.project_path
        assert restored.total_cost == original.total_cost
        assert restored.total_turns == original.total_turns
        assert restored.message_count == original.message_count
        assert restored.tools_used == original.tools_used


class TestInMemorySessionStorage:
    """Test in-memory session storage."""

    @pytest.fixture
    def storage(self):
        """Create storage instance."""
        return InMemorySessionStorage()

    @pytest.fixture
    def sample_session(self):
        """Create sample session."""
        return ClaudeSession(
            session_id="test-session",
            user_id=123,
            project_path=Path("/test/path"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )

    async def test_save_and_load_session(self, storage, sample_session):
        """Test saving and loading session."""
        # Save session
        await storage.save_session(sample_session)

        # Load session
        loaded = await storage.load_session("test-session")
        assert loaded is not None
        assert loaded.session_id == sample_session.session_id
        assert loaded.user_id == sample_session.user_id

    async def test_load_nonexistent_session(self, storage):
        """Test loading non-existent session."""
        result = await storage.load_session("nonexistent")
        assert result is None

    async def test_delete_session(self, storage, sample_session):
        """Test deleting session."""
        # Save and then delete
        await storage.save_session(sample_session)
        await storage.delete_session("test-session")

        # Should no longer exist
        result = await storage.load_session("test-session")
        assert result is None

    async def test_get_user_sessions(self, storage):
        """Test getting user sessions."""
        # Create sessions for different users
        session1 = ClaudeSession(
            session_id="session1",
            user_id=123,
            project_path=Path("/test/path1"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        session2 = ClaudeSession(
            session_id="session2",
            user_id=123,
            project_path=Path("/test/path2"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        session3 = ClaudeSession(
            session_id="session3",
            user_id=456,
            project_path=Path("/test/path3"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )

        await storage.save_session(session1)
        await storage.save_session(session2)
        await storage.save_session(session3)

        # Get sessions for user 123
        user_sessions = await storage.get_user_sessions(123)
        assert len(user_sessions) == 2
        assert all(s.user_id == 123 for s in user_sessions)

        # Get sessions for user 456
        user_sessions = await storage.get_user_sessions(456)
        assert len(user_sessions) == 1
        assert user_sessions[0].user_id == 456


class TestSessionManager:
    """Test session manager."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            session_timeout_hours=24,
            max_sessions_per_user=2,
        )

    @pytest.fixture
    def storage(self):
        """Create storage instance."""
        return InMemorySessionStorage()

    @pytest.fixture
    def session_manager(self, config, storage):
        """Create session manager."""
        return SessionManager(config, storage)

    async def test_create_new_session(self, session_manager):
        """Test creating new session."""
        session = await session_manager.get_or_create_session(
            user_id=123,
            project_path=Path("/test/project"),
        )

        assert session.user_id == 123
        assert session.project_path == Path("/test/project")
        assert session.session_id is not None

    async def test_get_existing_session(self, session_manager):
        """Test getting existing session."""
        # Create session
        session1 = await session_manager.get_or_create_session(
            user_id=123,
            project_path=Path("/test/project"),
        )

        # Get same session
        session2 = await session_manager.get_or_create_session(
            user_id=123,
            project_path=Path("/test/project"),
            session_id=session1.session_id,
        )

        assert session1.session_id == session2.session_id

    async def test_session_limit_enforcement(self, session_manager):
        """Test session limit enforcement."""
        # Create maximum number of sessions
        session1 = await session_manager.get_or_create_session(
            user_id=123, project_path=Path("/test/project1")
        )
        session2 = await session_manager.get_or_create_session(
            user_id=123, project_path=Path("/test/project2")
        )

        # Creating third session should remove oldest
        session3 = await session_manager.get_or_create_session(
            user_id=123, project_path=Path("/test/project3")
        )

        # Should have only 2 sessions
        user_sessions = await session_manager._get_user_sessions(123)
        assert len(user_sessions) == 2

        # First session should be gone
        loaded_session1 = await session_manager.storage.load_session(
            session1.session_id
        )
        assert loaded_session1 is None
