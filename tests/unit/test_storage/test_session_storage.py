"""Unit tests for session_storage.py - Session persistence."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.claude.session import ClaudeSession
from src.storage.database import DatabaseManager
from src.storage.models import SessionModel
from src.storage.session_storage import SQLiteSessionStorage


@pytest.fixture
async def db_manager():
    """Create test database manager."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        manager = DatabaseManager(f"sqlite:///{db_path}")
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.fixture
async def session_storage(db_manager):
    """Create session storage instance."""
    return SQLiteSessionStorage(db_manager)


@pytest.fixture
def sample_session():
    """Create sample ClaudeSession for testing."""
    return ClaudeSession(
        session_id="test_session_123",
        user_id=12345,
        project_path=Path("/tmp/test_project"),
        created_at=datetime.utcnow(),
        last_used=datetime.utcnow(),
        total_cost=1.5,
        total_turns=3,
        message_count=5,
        tools_used=["Read", "Write", "Bash"],
    )


class TestSQLiteSessionStorage:
    """Test SQLite session storage implementation."""

    @pytest.mark.asyncio
    async def test_ensure_user_exists_creates_new_user(
        self, session_storage, db_manager
    ):
        """Test that _ensure_user_exists creates a new user if not exists."""
        user_id = 99999
        username = "testuser"

        # Ensure user doesn't exist yet
        async with db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
            )
            result = await cursor.fetchone()
            assert result is None

        # Call _ensure_user_exists
        await session_storage._ensure_user_exists(user_id, username)

        # Verify user was created
        async with db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT user_id, telegram_username, is_allowed FROM users WHERE user_id = ?",
                (user_id,),
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == user_id
            assert result[1] == username
            assert result[2] == 1  # is_allowed = True

    @pytest.mark.asyncio
    async def test_ensure_user_exists_skips_existing_user(
        self, session_storage, db_manager
    ):
        """Test that _ensure_user_exists doesn't create duplicate users."""
        user_id = 88888
        username = "existing_user"

        # Create user first time
        await session_storage._ensure_user_exists(user_id, username)

        # Try to create again
        await session_storage._ensure_user_exists(user_id, "different_name")

        # Verify only one user exists with original username
        async with db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*), telegram_username FROM users WHERE user_id = ?",
                (user_id,),
            )
            result = await cursor.fetchone()
            assert result[0] == 1  # Only one user
            assert result[1] == username  # Original username unchanged

    @pytest.mark.asyncio
    async def test_save_session_new_session(self, session_storage, sample_session):
        """Test saving a new session."""
        await session_storage.save_session(sample_session)

        # Verify session was saved
        loaded_session = await session_storage.load_session(sample_session.session_id)
        assert loaded_session is not None
        assert loaded_session.session_id == sample_session.session_id
        assert loaded_session.user_id == sample_session.user_id
        assert loaded_session.project_path == sample_session.project_path
        assert loaded_session.total_cost == sample_session.total_cost
        assert loaded_session.total_turns == sample_session.total_turns
        assert loaded_session.message_count == sample_session.message_count

    @pytest.mark.asyncio
    async def test_save_session_update_existing(
        self, session_storage, sample_session
    ):
        """Test updating an existing session."""
        # Save initial session
        await session_storage.save_session(sample_session)

        # Update session data
        sample_session.total_cost = 3.0
        sample_session.total_turns = 6
        sample_session.message_count = 10
        sample_session.last_used = datetime.utcnow() + timedelta(hours=1)

        # Save updated session
        await session_storage.save_session(sample_session)

        # Verify updates were saved
        loaded_session = await session_storage.load_session(sample_session.session_id)
        assert loaded_session is not None
        assert loaded_session.total_cost == 3.0
        assert loaded_session.total_turns == 6
        assert loaded_session.message_count == 10

    @pytest.mark.asyncio
    async def test_save_session_creates_user_if_missing(
        self, session_storage, db_manager
    ):
        """Test that saving a session creates the user if not exists."""
        new_session = ClaudeSession(
            session_id="new_session_456",
            user_id=77777,
            project_path=Path("/tmp/another_project"),
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )

        # Save session (should create user automatically)
        await session_storage.save_session(new_session)

        # Verify user was created
        async with db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?", (77777,)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == 77777

    @pytest.mark.asyncio
    async def test_load_session_existing(self, session_storage, sample_session):
        """Test loading an existing session."""
        # Save session first
        await session_storage.save_session(sample_session)

        # Load it back
        loaded_session = await session_storage.load_session(sample_session.session_id)

        assert loaded_session is not None
        assert loaded_session.session_id == sample_session.session_id
        assert loaded_session.user_id == sample_session.user_id
        assert str(loaded_session.project_path) == str(sample_session.project_path)
        assert loaded_session.total_cost == sample_session.total_cost
        assert loaded_session.total_turns == sample_session.total_turns
        assert loaded_session.message_count == sample_session.message_count

    @pytest.mark.asyncio
    async def test_load_session_nonexistent(self, session_storage):
        """Test loading a non-existent session returns None."""
        loaded_session = await session_storage.load_session("nonexistent_session_id")
        assert loaded_session is None

    @pytest.mark.asyncio
    async def test_load_session_preserves_datetime_types(
        self, session_storage, sample_session
    ):
        """Test that datetime fields are properly converted."""
        await session_storage.save_session(sample_session)

        loaded_session = await session_storage.load_session(sample_session.session_id)

        assert isinstance(loaded_session.created_at, datetime)
        assert isinstance(loaded_session.last_used, datetime)

    @pytest.mark.asyncio
    async def test_delete_session(self, session_storage, sample_session):
        """Test deleting a session marks it as inactive."""
        # Save session
        await session_storage.save_session(sample_session)

        # Delete session
        await session_storage.delete_session(sample_session.session_id)

        # Verify session is marked as inactive
        async with session_storage.db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT is_active FROM sessions WHERE session_id = ?",
                (sample_session.session_id,),
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == 0  # is_active = False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_session(self, session_storage):
        """Test deleting a non-existent session doesn't raise error."""
        # Should not raise an error
        await session_storage.delete_session("nonexistent_session")

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, session_storage, db_manager):
        """Test getting all sessions for a user."""
        user_id = 12345

        # Create user first
        await session_storage._ensure_user_exists(user_id)

        # Create multiple sessions for the user
        sessions = []
        for i in range(3):
            session = ClaudeSession(
                session_id=f"session_{i}",
                user_id=user_id,
                project_path=Path(f"/tmp/project_{i}"),
                created_at=datetime.utcnow(),
                last_used=datetime.utcnow() - timedelta(hours=i),
            )
            sessions.append(session)
            await session_storage.save_session(session)

        # Create a session for a different user
        other_session = ClaudeSession(
            session_id="other_session",
            user_id=99999,
            project_path=Path("/tmp/other_project"),
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        await session_storage.save_session(other_session)

        # Get user sessions
        user_sessions = await session_storage.get_user_sessions(user_id)

        # Verify correct sessions returned
        assert len(user_sessions) == 3
        session_ids = [s.session_id for s in user_sessions]
        assert "session_0" in session_ids
        assert "session_1" in session_ids
        assert "session_2" in session_ids
        assert "other_session" not in session_ids

    @pytest.mark.asyncio
    async def test_get_user_sessions_ordered_by_last_used(
        self, session_storage, db_manager
    ):
        """Test that user sessions are ordered by last_used DESC."""
        user_id = 54321

        await session_storage._ensure_user_exists(user_id)

        # Create sessions with different last_used times
        now = datetime.utcnow()
        session1 = ClaudeSession(
            session_id="oldest",
            user_id=user_id,
            project_path=Path("/tmp/project1"),
            created_at=now,
            last_used=now - timedelta(hours=10),
        )
        session2 = ClaudeSession(
            session_id="newest",
            user_id=user_id,
            project_path=Path("/tmp/project2"),
            created_at=now,
            last_used=now,
        )
        session3 = ClaudeSession(
            session_id="middle",
            user_id=user_id,
            project_path=Path("/tmp/project3"),
            created_at=now,
            last_used=now - timedelta(hours=5),
        )

        await session_storage.save_session(session1)
        await session_storage.save_session(session2)
        await session_storage.save_session(session3)

        # Get user sessions
        user_sessions = await session_storage.get_user_sessions(user_id)

        # Verify order (newest first)
        assert user_sessions[0].session_id == "newest"
        assert user_sessions[1].session_id == "middle"
        assert user_sessions[2].session_id == "oldest"

    @pytest.mark.asyncio
    async def test_get_user_sessions_empty(self, session_storage):
        """Test getting sessions for user with no sessions."""
        user_sessions = await session_storage.get_user_sessions(99999)
        assert user_sessions == []

    @pytest.mark.asyncio
    async def test_get_user_sessions_excludes_inactive(
        self, session_storage, db_manager
    ):
        """Test that inactive sessions are excluded."""
        user_id = 11111

        await session_storage._ensure_user_exists(user_id)

        # Create active session
        active_session = ClaudeSession(
            session_id="active",
            user_id=user_id,
            project_path=Path("/tmp/active"),
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        await session_storage.save_session(active_session)

        # Create inactive session
        inactive_session = ClaudeSession(
            session_id="inactive",
            user_id=user_id,
            project_path=Path("/tmp/inactive"),
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        await session_storage.save_session(inactive_session)
        await session_storage.delete_session("inactive")

        # Get user sessions
        user_sessions = await session_storage.get_user_sessions(user_id)

        # Should only include active session
        assert len(user_sessions) == 1
        assert user_sessions[0].session_id == "active"

    @pytest.mark.asyncio
    async def test_get_all_sessions(self, session_storage, db_manager):
        """Test getting all active sessions."""
        # Create sessions for multiple users
        for user_id in [111, 222, 333]:
            await session_storage._ensure_user_exists(user_id)
            session = ClaudeSession(
                session_id=f"session_user_{user_id}",
                user_id=user_id,
                project_path=Path(f"/tmp/project_{user_id}"),
                created_at=datetime.utcnow(),
                last_used=datetime.utcnow(),
            )
            await session_storage.save_session(session)

        # Get all sessions
        all_sessions = await session_storage.get_all_sessions()

        # Verify all sessions returned
        assert len(all_sessions) == 3
        session_ids = [s.session_id for s in all_sessions]
        assert "session_user_111" in session_ids
        assert "session_user_222" in session_ids
        assert "session_user_333" in session_ids

    @pytest.mark.asyncio
    async def test_get_all_sessions_excludes_inactive(
        self, session_storage, db_manager
    ):
        """Test that get_all_sessions excludes inactive sessions."""
        # Create active session
        await session_storage._ensure_user_exists(111)
        active_session = ClaudeSession(
            session_id="active_session",
            user_id=111,
            project_path=Path("/tmp/active"),
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        await session_storage.save_session(active_session)

        # Create and delete inactive session
        await session_storage._ensure_user_exists(222)
        inactive_session = ClaudeSession(
            session_id="inactive_session",
            user_id=222,
            project_path=Path("/tmp/inactive"),
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        await session_storage.save_session(inactive_session)
        await session_storage.delete_session("inactive_session")

        # Get all sessions
        all_sessions = await session_storage.get_all_sessions()

        # Should only include active session
        assert len(all_sessions) == 1
        assert all_sessions[0].session_id == "active_session"

    @pytest.mark.asyncio
    async def test_get_all_sessions_ordered(self, session_storage, db_manager):
        """Test that all sessions are ordered by last_used DESC."""
        now = datetime.utcnow()

        for i, hours_ago in enumerate([5, 1, 10]):
            await session_storage._ensure_user_exists(i)
            session = ClaudeSession(
                session_id=f"session_{i}",
                user_id=i,
                project_path=Path(f"/tmp/project_{i}"),
                created_at=now,
                last_used=now - timedelta(hours=hours_ago),
            )
            await session_storage.save_session(session)

        all_sessions = await session_storage.get_all_sessions()

        # Verify order (newest first)
        assert all_sessions[0].session_id == "session_1"  # 1 hour ago
        assert all_sessions[1].session_id == "session_0"  # 5 hours ago
        assert all_sessions[2].session_id == "session_2"  # 10 hours ago

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, session_storage, db_manager):
        """Test cleanup of expired sessions."""
        now = datetime.utcnow()
        timeout_hours = 24

        # Create recent session (not expired)
        await session_storage._ensure_user_exists(111)
        recent_session = ClaudeSession(
            session_id="recent",
            user_id=111,
            project_path=Path("/tmp/recent"),
            created_at=now,
            last_used=now - timedelta(hours=12),
        )
        await session_storage.save_session(recent_session)

        # Create expired session
        await session_storage._ensure_user_exists(222)
        expired_session = ClaudeSession(
            session_id="expired",
            user_id=222,
            project_path=Path("/tmp/expired"),
            created_at=now - timedelta(hours=48),
            last_used=now - timedelta(hours=48),
        )
        await session_storage.save_session(expired_session)

        # Run cleanup
        affected = await session_storage.cleanup_expired_sessions(timeout_hours)

        # Verify one session was cleaned up
        assert affected == 1

        # Verify expired session is now inactive
        async with session_storage.db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT is_active FROM sessions WHERE session_id = 'expired'"
            )
            result = await cursor.fetchone()
            assert result[0] == 0  # is_active = False

        # Verify recent session is still active
        async with session_storage.db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT is_active FROM sessions WHERE session_id = 'recent'"
            )
            result = await cursor.fetchone()
            assert result[0] == 1  # is_active = True

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_returns_count(
        self, session_storage, db_manager
    ):
        """Test that cleanup returns correct count of affected sessions."""
        now = datetime.utcnow()

        # Create multiple expired sessions
        for i in range(5):
            await session_storage._ensure_user_exists(i)
            session = ClaudeSession(
                session_id=f"expired_{i}",
                user_id=i,
                project_path=Path(f"/tmp/expired_{i}"),
                created_at=now - timedelta(hours=48),
                last_used=now - timedelta(hours=48),
            )
            await session_storage.save_session(session)

        # Run cleanup
        affected = await session_storage.cleanup_expired_sessions(24)

        # Verify correct count
        assert affected == 5

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_no_expired(self, session_storage):
        """Test cleanup when no sessions are expired."""
        now = datetime.utcnow()

        # Create only recent sessions
        for i in range(3):
            await session_storage._ensure_user_exists(i)
            session = ClaudeSession(
                session_id=f"recent_{i}",
                user_id=i,
                project_path=Path(f"/tmp/recent_{i}"),
                created_at=now,
                last_used=now - timedelta(hours=1),
            )
            await session_storage.save_session(session)

        # Run cleanup
        affected = await session_storage.cleanup_expired_sessions(24)

        # Verify no sessions were affected
        assert affected == 0

    @pytest.mark.asyncio
    async def test_session_tools_tracking(self, session_storage, sample_session):
        """Test that sessions can be saved and loaded (tools tracked separately)."""
        # Sample session has tools_used, but storage doesn't persist them directly
        sample_session.tools_used = ["Read", "Write", "Bash"]

        await session_storage.save_session(sample_session)
        loaded_session = await session_storage.load_session(sample_session.session_id)

        # Tools should be empty list (tracked separately in tool_usage table)
        assert loaded_session.tools_used == []

    @pytest.mark.asyncio
    async def test_concurrent_session_saves(self, session_storage, db_manager):
        """Test concurrent session save operations."""
        import asyncio

        user_id = 555
        await session_storage._ensure_user_exists(user_id)

        # Create multiple sessions
        sessions = []
        for i in range(10):
            session = ClaudeSession(
                session_id=f"concurrent_{i}",
                user_id=user_id,
                project_path=Path(f"/tmp/concurrent_{i}"),
                created_at=datetime.utcnow(),
                last_used=datetime.utcnow(),
            )
            sessions.append(session)

        # Save all sessions concurrently
        await asyncio.gather(*[session_storage.save_session(s) for s in sessions])

        # Verify all sessions were saved
        user_sessions = await session_storage.get_user_sessions(user_id)
        assert len(user_sessions) == 10
