"""Tests for repository implementations."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.storage.database import DatabaseManager
from src.storage.models import (
    MessageModel,
    ProjectThreadModel,
    SessionModel,
    ToolUsageModel,
    UserModel,
)
from src.storage.repositories import (
    AnalyticsRepository,
    AuditLogRepository,
    MessageRepository,
    ProjectThreadRepository,
    SessionRepository,
    ToolUsageRepository,
    UserRepository,
)


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
async def user_repo(db_manager):
    """Create user repository."""
    return UserRepository(db_manager)


@pytest.fixture
async def session_repo(db_manager):
    """Create session repository."""
    return SessionRepository(db_manager)


@pytest.fixture
async def message_repo(db_manager):
    """Create message repository."""
    return MessageRepository(db_manager)


@pytest.fixture
async def tool_repo(db_manager):
    """Create tool usage repository."""
    return ToolUsageRepository(db_manager)


@pytest.fixture
async def audit_repo(db_manager):
    """Create audit log repository."""
    return AuditLogRepository(db_manager)


@pytest.fixture
async def analytics_repo(db_manager):
    """Create analytics repository."""
    return AnalyticsRepository(db_manager)


@pytest.fixture
async def project_thread_repo(db_manager):
    """Create project thread repository."""
    return ProjectThreadRepository(db_manager)


class TestUserRepository:
    """Test user repository."""

    async def test_create_and_get_user(self, user_repo):
        """Test creating and retrieving user."""
        user = UserModel(
            user_id=12345,
            telegram_username="testuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )

        # Create user
        created_user = await user_repo.create_user(user)
        assert created_user.user_id == 12345

        # Get user
        retrieved_user = await user_repo.get_user(12345)
        assert retrieved_user is not None
        assert retrieved_user.user_id == 12345
        assert retrieved_user.telegram_username == "testuser"
        assert retrieved_user.is_allowed == 1  # SQLite stores boolean as integer

    async def test_update_user(self, user_repo):
        """Test updating user."""
        user = UserModel(
            user_id=12346,
            telegram_username="testuser2",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=False,
            total_cost=10.5,
            message_count=5,
        )

        await user_repo.create_user(user)

        # Update user
        user.total_cost = 20.0
        user.message_count = 10
        await user_repo.update_user(user)

        # Verify update
        updated_user = await user_repo.get_user(12346)
        assert updated_user.total_cost == 20.0
        assert updated_user.message_count == 10

    async def test_get_allowed_users(self, user_repo):
        """Test getting allowed users."""
        # Create allowed user
        allowed_user = UserModel(
            user_id=12347,
            telegram_username="allowed",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(allowed_user)

        # Create disallowed user
        disallowed_user = UserModel(
            user_id=12348,
            telegram_username="disallowed",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=False,
        )
        await user_repo.create_user(disallowed_user)

        # Get allowed users
        allowed_users = await user_repo.get_allowed_users()
        assert 12347 in allowed_users
        assert 12348 not in allowed_users


class TestSessionRepository:
    """Test session repository."""

    async def test_create_and_get_session(self, session_repo, user_repo):
        """Test creating and retrieving session."""
        # Create user first
        user = UserModel(
            user_id=12349,
            telegram_username="sessionuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        # Create session
        session = SessionModel(
            session_id="test-session-123",
            user_id=12349,
            project_path="/test/project",
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
            total_cost=5.0,
            total_turns=3,
            message_count=2,
        )

        created_session = await session_repo.create_session(session)
        assert created_session.session_id == "test-session-123"

        # Get session
        retrieved_session = await session_repo.get_session("test-session-123")
        assert retrieved_session is not None
        assert retrieved_session.user_id == 12349
        assert retrieved_session.project_path == "/test/project"

    async def test_get_user_sessions(self, session_repo, user_repo):
        """Test getting user sessions."""
        # Create user
        user = UserModel(
            user_id=12350,
            telegram_username="multisessionuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        # Create multiple sessions
        for i in range(3):
            session = SessionModel(
                session_id=f"test-session-{i}",
                user_id=12350,
                project_path=f"/test/project{i}",
                created_at=datetime.now(UTC),
                last_used=datetime.now(UTC),
            )
            await session_repo.create_session(session)

        # Get user sessions
        sessions = await session_repo.get_user_sessions(12350)
        assert len(sessions) == 3
        assert all(s.user_id == 12350 for s in sessions)

    async def test_cleanup_old_sessions(self, session_repo, user_repo):
        """Test cleaning up old sessions."""
        # Create user
        user = UserModel(
            user_id=12351,
            telegram_username="cleanupuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        # Create old session
        old_session = SessionModel(
            session_id="old-session",
            user_id=12351,
            project_path="/test/old",
            created_at=datetime.now(UTC) - timedelta(days=35),
            last_used=datetime.now(UTC) - timedelta(days=35),
        )
        await session_repo.create_session(old_session)

        # Create recent session
        recent_session = SessionModel(
            session_id="recent-session",
            user_id=12351,
            project_path="/test/recent",
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        await session_repo.create_session(recent_session)

        # Cleanup old sessions
        cleaned = await session_repo.cleanup_old_sessions(days=30)
        assert cleaned == 1

        # Check that only recent session is active
        active_sessions = await session_repo.get_user_sessions(12351, active_only=True)
        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == "recent-session"


class TestMessageRepository:
    """Test message repository."""

    async def test_save_and_get_messages(self, message_repo, session_repo, user_repo):
        """Test saving and retrieving messages."""
        # Setup user and session
        user = UserModel(
            user_id=12352,
            telegram_username="messageuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        session = SessionModel(
            session_id="message-session",
            user_id=12352,
            project_path="/test/messages",
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        await session_repo.create_session(session)

        # Save message
        message = MessageModel(
            session_id="message-session",
            user_id=12352,
            timestamp=datetime.now(UTC),
            prompt="Test prompt",
            response="Test response",
            cost=0.05,
            duration_ms=1500,
        )

        message_id = await message_repo.save_message(message)
        assert message_id is not None

        # Get session messages
        messages = await message_repo.get_session_messages("message-session")
        assert len(messages) == 1
        assert messages[0].prompt == "Test prompt"
        assert messages[0].response == "Test response"


class TestProjectThreadRepository:
    """Test project thread repository."""

    async def test_upsert_and_lookup(self, project_thread_repo):
        """Upsert creates mapping and lookup resolves it."""
        mapping = await project_thread_repo.upsert_mapping(
            project_slug="app1",
            chat_id=-1001234567890,
            message_thread_id=321,
            topic_name="App One",
        )

        assert isinstance(mapping, ProjectThreadModel)
        assert mapping.project_slug == "app1"
        assert mapping.message_thread_id == 321

        lookup = await project_thread_repo.get_by_chat_thread(-1001234567890, 321)
        assert lookup is not None
        assert lookup.project_slug == "app1"

    async def test_deactivate_missing_projects(self, project_thread_repo):
        """Mappings not in active set are deactivated."""
        await project_thread_repo.upsert_mapping(
            project_slug="app1",
            chat_id=-1001234567890,
            message_thread_id=111,
            topic_name="App 1",
        )
        await project_thread_repo.upsert_mapping(
            project_slug="app2",
            chat_id=-1001234567890,
            message_thread_id=222,
            topic_name="App 2",
        )

        changed = await project_thread_repo.deactivate_missing_projects(
            chat_id=-1001234567890,
            active_project_slugs=["app1"],
        )

        assert changed == 1
        inactive_mapping = await project_thread_repo.get_by_chat_project(
            -1001234567890, "app2"
        )
        assert inactive_mapping is not None
        assert inactive_mapping.is_active is False

    async def test_list_stale_active_mappings(self, project_thread_repo):
        """Returns only active mappings not in enabled project set."""
        await project_thread_repo.upsert_mapping(
            project_slug="app1",
            chat_id=-1001234567890,
            message_thread_id=111,
            topic_name="App 1",
            is_active=True,
        )
        await project_thread_repo.upsert_mapping(
            project_slug="app2",
            chat_id=-1001234567890,
            message_thread_id=222,
            topic_name="App 2",
            is_active=True,
        )
        await project_thread_repo.upsert_mapping(
            project_slug="app3",
            chat_id=-1001234567890,
            message_thread_id=333,
            topic_name="App 3",
            is_active=False,
        )

        stale = await project_thread_repo.list_stale_active_mappings(
            chat_id=-1001234567890,
            active_project_slugs=["app1"],
        )

        assert len(stale) == 1
        assert stale[0].project_slug == "app2"

    async def test_set_active_updates_flag(self, project_thread_repo):
        """set_active toggles mapping active flag."""
        await project_thread_repo.upsert_mapping(
            project_slug="app1",
            chat_id=-1001234567890,
            message_thread_id=111,
            topic_name="App 1",
            is_active=True,
        )

        changed = await project_thread_repo.set_active(
            chat_id=-1001234567890,
            project_slug="app1",
            is_active=False,
        )

        assert changed == 1
        mapping = await project_thread_repo.get_by_chat_project(-1001234567890, "app1")
        assert mapping is not None
        assert mapping.is_active is False


class TestToolUsageRepository:
    """Test tool usage repository."""

    async def test_save_and_get_tool_usage(self, tool_repo, session_repo, user_repo):
        """Test saving and retrieving tool usage."""
        # Setup user and session
        user = UserModel(
            user_id=12353,
            telegram_username="tooluser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        session = SessionModel(
            session_id="tool-session",
            user_id=12353,
            project_path="/test/tools",
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        await session_repo.create_session(session)

        # Save tool usage
        tool_usage = ToolUsageModel(
            session_id="tool-session",
            tool_name="Read",
            tool_input={"file_path": "/test/file.py"},
            timestamp=datetime.now(UTC),
            success=True,
        )

        usage_id = await tool_repo.save_tool_usage(tool_usage)
        assert usage_id is not None

        # Get session tool usage
        usage_records = await tool_repo.get_session_tool_usage("tool-session")
        assert len(usage_records) == 1
        assert usage_records[0].tool_name == "Read"
        assert usage_records[0].tool_input["file_path"] == "/test/file.py"

    async def test_get_tool_stats(self, tool_repo, session_repo, user_repo):
        """Test getting tool statistics."""
        # Setup user and session
        user = UserModel(
            user_id=12354,
            telegram_username="statsuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        session = SessionModel(
            session_id="stats-session",
            user_id=12354,
            project_path="/test/stats",
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        await session_repo.create_session(session)

        # Create multiple tool usages
        tools = ["Read", "Write", "Read", "Edit", "Read"]
        for tool in tools:
            tool_usage = ToolUsageModel(
                session_id="stats-session",
                tool_name=tool,
                timestamp=datetime.now(UTC),
                success=True,
            )
            await tool_repo.save_tool_usage(tool_usage)

        # Get tool stats
        stats = await tool_repo.get_tool_stats()

        # Find Read tool stats
        read_stats = next(s for s in stats if s["tool_name"] == "Read")
        assert read_stats["usage_count"] == 3
        assert read_stats["success_count"] == 3
        assert read_stats["error_count"] == 0


class TestAnalyticsRepository:
    """Test analytics repository."""

    async def test_get_system_stats(
        self, analytics_repo, message_repo, session_repo, user_repo
    ):
        """Test getting system statistics."""
        # Setup test data
        user = UserModel(
            user_id=12355,
            telegram_username="analyticsuser",
            first_seen=datetime.now(UTC),
            last_active=datetime.now(UTC),
            is_allowed=True,
        )
        await user_repo.create_user(user)

        session = SessionModel(
            session_id="analytics-session",
            user_id=12355,
            project_path="/test/analytics",
            created_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
        )
        await session_repo.create_session(session)

        # Create messages
        for i in range(3):
            message = MessageModel(
                session_id="analytics-session",
                user_id=12355,
                timestamp=datetime.now(UTC),
                prompt=f"Test prompt {i}",
                response=f"Test response {i}",
                cost=0.1,
            )
            await message_repo.save_message(message)

        # Get system stats
        stats = await analytics_repo.get_system_stats()

        assert stats["overall"]["total_users"] >= 1
        assert stats["overall"]["total_sessions"] >= 1
        assert stats["overall"]["total_messages"] >= 3
        assert stats["overall"]["total_cost"] >= 0.3
