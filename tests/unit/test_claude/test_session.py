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

    def test_from_dict_normalizes_legacy_naive_timestamps(self):
        """Legacy naive timestamps should be normalized to UTC-aware datetimes."""
        data = {
            "session_id": "test-session",
            "user_id": 123,
            "project_path": "/test/path",
            "created_at": "2026-02-18T10:00:00",
            "last_used": "2026-02-18T10:30:00",
            "total_cost": 0.0,
            "total_turns": 0,
            "message_count": 0,
            "tools_used": [],
        }

        restored = ClaudeSession.from_dict(data)

        assert restored.created_at.tzinfo is not None
        assert restored.last_used.tzinfo is not None
        assert restored.created_at.tzinfo == UTC
        assert restored.last_used.tzinfo == UTC

    def test_is_expired_handles_legacy_naive_last_used(self):
        """Expiry check should not crash on naive legacy timestamps."""
        now_utc = datetime.now(UTC)
        naive_old = (now_utc - timedelta(hours=30)).replace(tzinfo=None)
        session = ClaudeSession(
            session_id="legacy-session",
            user_id=123,
            project_path=Path("/test/path"),
            created_at=naive_old,
            last_used=naive_old,
        )

        assert session.is_expired(24) is True


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

        # Load session with correct user_id
        loaded = await storage.load_session("test-session", user_id=123)
        assert loaded is not None
        assert loaded.session_id == sample_session.session_id
        assert loaded.user_id == sample_session.user_id

    async def test_load_nonexistent_session(self, storage):
        """Test loading non-existent session."""
        result = await storage.load_session("nonexistent", user_id=123)
        assert result is None

    async def test_load_session_wrong_user(self, storage, sample_session):
        """Test that loading a session with wrong user_id returns None."""
        await storage.save_session(sample_session)

        # Load with wrong user_id should return None
        result = await storage.load_session("test-session", user_id=999)
        assert result is None

    async def test_delete_session(self, storage, sample_session):
        """Test deleting session."""
        # Save and then delete
        await storage.save_session(sample_session)
        await storage.delete_session("test-session")

        # Should no longer exist
        result = await storage.load_session("test-session", user_id=123)
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
        assert session.is_new_session is True
        assert session.session_id == ""  # Empty until Claude responds

    async def test_get_existing_session(self, session_manager):
        """Test getting existing session by ID after it has a real session_id."""
        # Simulate a session that has already received a real ID from Claude
        existing = ClaudeSession(
            session_id="real-session-id",
            user_id=123,
            project_path=Path("/test/project"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        await session_manager.storage.save_session(existing)
        session_manager.active_sessions["real-session-id"] = existing

        # Get same session by ID
        session2 = await session_manager.get_or_create_session(
            user_id=123,
            project_path=Path("/test/project"),
            session_id="real-session-id",
        )

        assert session2.session_id == "real-session-id"

    async def test_session_limit_enforcement(self, session_manager):
        """Test session limit enforcement."""
        # Seed sessions that have already received real IDs (simulating
        # the full create -> Claude responds -> update_session lifecycle)
        for i, path in enumerate(["/test/project1", "/test/project2"], start=1):
            s = ClaudeSession(
                session_id=f"session-{i}",
                user_id=123,
                project_path=Path(path),
                created_at=datetime.now(UTC),
                last_used=datetime.now(UTC) - timedelta(hours=i),  # older = higher i
            )
            await session_manager.storage.save_session(s)
            session_manager.active_sessions[s.session_id] = s

        # Verify we have 2 sessions
        assert len(await session_manager._get_user_sessions(123)) == 2

        # Creating third session should remove the oldest (session-2)
        await session_manager.get_or_create_session(
            user_id=123, project_path=Path("/test/project3")
        )

        # After eviction, only session-1 remains persisted
        # (session-2 evicted, session-3 is new/unsaved so not yet in storage)
        persisted = await session_manager._get_user_sessions(123)
        assert len(persisted) == 1  # Only session-1 persisted
        assert persisted[0].session_id == "session-1"

        # session-2 should be gone
        loaded = await session_manager.storage.load_session("session-2", user_id=123)
        assert loaded is None

    async def test_get_or_create_rejects_wrong_user_active_cache(self, session_manager):
        """Requesting another user's session via active cache creates a new one."""
        existing = ClaudeSession(
            session_id="other-user-session",
            user_id=999,
            project_path=Path("/test/project"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        session_manager.active_sessions["other-user-session"] = existing

        # User 123 tries to resume user 999's session
        session = await session_manager.get_or_create_session(
            user_id=123,
            project_path=Path("/test/project"),
            session_id="other-user-session",
        )

        # Should get a new session, not the other user's
        assert session.session_id != "other-user-session"
        assert session.user_id == 123
        assert session.is_new_session is True

    async def test_get_or_create_rejects_wrong_user_from_storage(self, session_manager):
        """Requesting another user's session via storage creates a new one."""
        existing = ClaudeSession(
            session_id="stored-other-session",
            user_id=999,
            project_path=Path("/test/project"),
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        await session_manager.storage.save_session(existing)

        # User 123 tries to resume user 999's session
        session = await session_manager.get_or_create_session(
            user_id=123,
            project_path=Path("/test/project"),
            session_id="stored-other-session",
        )

        # Should get a new session, not the other user's
        assert session.session_id != "stored-other-session"
        assert session.user_id == 123
        assert session.is_new_session is True


class TestUpdateSessionNewWithoutId:
    """Edge case: Claude returns no session_id for a brand-new session."""

    @pytest.fixture
    def config(self, tmp_path):
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            session_timeout_hours=24,
            max_sessions_per_user=2,
        )

    @pytest.fixture
    def session_manager(self, config):
        return SessionManager(config, InMemorySessionStorage())

    async def test_warns_and_does_not_persist(self, session_manager):
        """When Claude returns no session_id, session is not persisted."""
        session = await session_manager.get_or_create_session(
            user_id=999, project_path=Path("/test/no-id")
        )
        assert session.is_new_session is True

        # Simulate Claude returning empty session_id
        response = ClaudeResponse(
            content="hello",
            session_id="",
            cost=0.001,
            duration_ms=50,
            num_turns=1,
        )

        await session_manager.update_session(session, response)

        # Session should be marked as no longer new
        assert session.is_new_session is False

        # Session should NOT be persisted (empty session_id)
        assert len(session_manager.active_sessions) == 0
        persisted = await session_manager._get_user_sessions(999)
        assert len(persisted) == 0
