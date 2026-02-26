"""Tests for SessionMemoryRepository."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.storage.database import DatabaseManager
from src.storage.models import SessionMemoryModel, SessionModel, UserModel
from src.storage.repositories import (
    SessionMemoryRepository,
    SessionRepository,
    UserRepository,
)


@pytest.fixture
async def db_manager():
    """Create test database manager with in-memory-like temp DB."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        manager = DatabaseManager(f"sqlite:///{db_path}")
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.fixture
async def user_repo(db_manager):
    """Create user repository."""
    return UserRepository(db_manager)


@pytest.fixture
async def session_repo(db_manager):
    """Create session repository."""
    return SessionRepository(db_manager)


@pytest.fixture
async def memory_repo(db_manager):
    """Create session memory repository."""
    return SessionMemoryRepository(db_manager)


async def _seed_user_and_session(
    user_repo: UserRepository,
    session_repo: SessionRepository,
    user_id: int = 12345,
    session_id: str = "test-session-1",
    project_path: str = "/test/project",
) -> None:
    """Seed a user and session for foreign key constraints."""
    user = UserModel(
        user_id=user_id,
        telegram_username="testuser",
        first_seen=datetime.now(UTC),
        last_active=datetime.now(UTC),
        is_allowed=True,
    )
    await user_repo.create_user(user)

    session = SessionModel(
        session_id=session_id,
        user_id=user_id,
        project_path=project_path,
        created_at=datetime.now(UTC),
        last_used=datetime.now(UTC),
    )
    await session_repo.create_session(session)


class TestSessionMemoryRepository:
    """Tests for SessionMemoryRepository."""

    async def test_save_memory_returns_row_id(
        self, memory_repo, user_repo, session_repo
    ):
        """save_memory inserts a record and returns the row id."""
        await _seed_user_and_session(user_repo, session_repo)

        row_id = await memory_repo.save_memory(
            user_id=12345,
            project_path="/test/project",
            session_id="test-session-1",
            summary="User worked on feature X.",
        )

        assert row_id is not None
        assert isinstance(row_id, int)
        assert row_id > 0

    async def test_get_active_memories_returns_newest_first(
        self, memory_repo, user_repo, session_repo
    ):
        """get_active_memories returns active memories in descending order."""
        # Seed multiple sessions for distinct session_ids
        user_id = 12345
        project_path = "/test/project"

        user = UserModel(
            user_id=user_id,
            telegram_username="testuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        for i in range(3):
            session = SessionModel(
                session_id=f"sess-{i}",
                user_id=user_id,
                project_path=project_path,
                created_at=datetime.now(UTC),
                last_used=datetime.now(UTC),
            )
            await session_repo.create_session(session)

        # Insert memories (they get created_at from DB default CURRENT_TIMESTAMP)
        summaries = ["First summary", "Second summary", "Third summary"]
        for i, summary in enumerate(summaries):
            await memory_repo.save_memory(
                user_id=user_id,
                project_path=project_path,
                session_id=f"sess-{i}",
                summary=summary,
            )

        memories = await memory_repo.get_active_memories(
            user_id=user_id,
            project_path=project_path,
            limit=10,
        )

        assert len(memories) == 3
        assert all(isinstance(m, SessionMemoryModel) for m in memories)
        # Newest first (DESC order by created_at); since inserted sequentially
        # with CURRENT_TIMESTAMP, the last inserted should be first
        assert memories[0].summary == "Third summary"
        assert memories[2].summary == "First summary"

    async def test_get_active_memories_returns_empty_when_none_exist(self, memory_repo):
        """get_active_memories returns empty list when no memories exist."""
        memories = await memory_repo.get_active_memories(
            user_id=99999,
            project_path="/nonexistent/path",
            limit=5,
        )

        assert memories == []

    async def test_get_active_memories_respects_limit(
        self, memory_repo, user_repo, session_repo
    ):
        """get_active_memories respects the limit parameter."""
        user_id = 12345
        project_path = "/test/project"

        user = UserModel(
            user_id=user_id,
            telegram_username="testuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        for i in range(5):
            session = SessionModel(
                session_id=f"limit-sess-{i}",
                user_id=user_id,
                project_path=project_path,
                created_at=datetime.now(UTC),
                last_used=datetime.now(UTC),
            )
            await session_repo.create_session(session)
            await memory_repo.save_memory(
                user_id=user_id,
                project_path=project_path,
                session_id=f"limit-sess-{i}",
                summary=f"Summary {i}",
            )

        memories = await memory_repo.get_active_memories(
            user_id=user_id,
            project_path=project_path,
            limit=2,
        )

        assert len(memories) == 2

    async def test_deactivate_old_memories_beyond_keep_count(
        self, memory_repo, user_repo, session_repo
    ):
        """deactivate_old_memories deactivates oldest memories beyond keep_count."""
        user_id = 12345
        project_path = "/test/project"

        user = UserModel(
            user_id=user_id,
            telegram_username="testuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        # Create 5 sessions and memories
        for i in range(5):
            session = SessionModel(
                session_id=f"deact-sess-{i}",
                user_id=user_id,
                project_path=project_path,
                created_at=datetime.now(UTC),
                last_used=datetime.now(UTC),
            )
            await session_repo.create_session(session)
            await memory_repo.save_memory(
                user_id=user_id,
                project_path=project_path,
                session_id=f"deact-sess-{i}",
                summary=f"Summary {i}",
            )

        # Keep only 2 newest
        deactivated = await memory_repo.deactivate_old_memories(
            user_id=user_id,
            project_path=project_path,
            keep_count=2,
        )

        assert deactivated == 3

        # Only 2 active memories should remain
        active = await memory_repo.get_active_memories(
            user_id=user_id,
            project_path=project_path,
            limit=10,
        )
        assert len(active) == 2

    async def test_deactivate_old_memories_no_op_when_under_limit(
        self, memory_repo, user_repo, session_repo
    ):
        """deactivate_old_memories does nothing when count <= keep_count."""
        await _seed_user_and_session(user_repo, session_repo)

        await memory_repo.save_memory(
            user_id=12345,
            project_path="/test/project",
            session_id="test-session-1",
            summary="Only memory",
        )

        deactivated = await memory_repo.deactivate_old_memories(
            user_id=12345,
            project_path="/test/project",
            keep_count=5,
        )

        assert deactivated == 0

        # Memory should still be active
        active = await memory_repo.get_active_memories(
            user_id=12345,
            project_path="/test/project",
            limit=10,
        )
        assert len(active) == 1

    async def test_get_active_memories_excludes_inactive(
        self, memory_repo, user_repo, session_repo
    ):
        """get_active_memories only returns memories where is_active=TRUE."""
        user_id = 12345
        project_path = "/test/project"

        user = UserModel(
            user_id=user_id,
            telegram_username="testuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        # Create 4 sessions and memories
        for i in range(4):
            session = SessionModel(
                session_id=f"inactive-sess-{i}",
                user_id=user_id,
                project_path=project_path,
                created_at=datetime.now(UTC),
                last_used=datetime.now(UTC),
            )
            await session_repo.create_session(session)
            await memory_repo.save_memory(
                user_id=user_id,
                project_path=project_path,
                session_id=f"inactive-sess-{i}",
                summary=f"Summary {i}",
            )

        # Deactivate keeping only 1
        await memory_repo.deactivate_old_memories(
            user_id=user_id,
            project_path=project_path,
            keep_count=1,
        )

        active = await memory_repo.get_active_memories(
            user_id=user_id,
            project_path=project_path,
            limit=10,
        )
        assert len(active) == 1
