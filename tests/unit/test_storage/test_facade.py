"""Tests for storage facade."""

import tempfile
from datetime import datetime  # noqa: F401
from pathlib import Path

import pytest

from src.claude.integration import ClaudeResponse
from src.storage.facade import Storage


@pytest.fixture
async def storage():
    """Create test storage."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        storage = Storage(f"sqlite:///{db_path}")
        await storage.initialize()
        yield storage
        await storage.close()


class TestStorageFacade:
    """Test storage facade functionality."""

    async def test_initialization(self, storage):
        """Test storage initialization."""
        # Should be able to perform health check
        assert await storage.health_check()

    async def test_get_or_create_user(self, storage):
        """Test getting or creating user."""
        # Create new user
        user = await storage.get_or_create_user(12345, "testuser")
        assert user.user_id == 12345
        assert user.telegram_username == "testuser"
        assert not user.is_allowed  # Default to not allowed

        # Get existing user
        user2 = await storage.get_or_create_user(12345, "testuser")
        assert user2.user_id == 12345
        assert user2.telegram_username == "testuser"

    async def test_create_session(self, storage):
        """Test creating session."""
        # Create user first
        await storage.get_or_create_user(12346, "sessionuser")

        # Create session
        session = await storage.create_session(
            12346, "/test/project", "test-session-123"
        )
        assert session.session_id == "test-session-123"
        assert session.user_id == 12346
        assert session.project_path == "/test/project"

        # User session count should be updated
        updated_user = await storage.users.get_user(12346)
        assert updated_user.session_count == 1

    async def test_save_claude_interaction(self, storage):
        """Test saving Claude interaction."""
        # Setup user and session
        await storage.get_or_create_user(12347, "claudeuser")
        await storage.create_session(12347, "/test/claude", "claude-session")

        # Create Claude response
        claude_response = ClaudeResponse(
            content="Test response content",
            session_id="claude-session",
            cost=0.05,
            duration_ms=1500,
            num_turns=1,
            tools_used=[{"name": "Read", "input": {"file_path": "/test/file.py"}}],
        )

        # Save interaction
        await storage.save_claude_interaction(
            user_id=12347,
            session_id="claude-session",
            prompt="Test prompt",
            response=claude_response,
        )

        # Verify data was saved
        # Check message was saved
        messages = await storage.messages.get_session_messages("claude-session")
        assert len(messages) == 1
        assert messages[0].prompt == "Test prompt"
        assert messages[0].response == "Test response content"
        assert messages[0].cost == 0.05

        # Check tool usage was saved
        tool_usage = await storage.tools.get_session_tool_usage("claude-session")
        assert len(tool_usage) == 1
        assert tool_usage[0].tool_name == "Read"

        # Check user stats were updated
        updated_user = await storage.users.get_user(12347)
        assert updated_user.total_cost == 0.05
        assert updated_user.message_count == 1

        # Check session stats were updated
        updated_session = await storage.sessions.get_session("claude-session")
        assert updated_session.total_cost == 0.05
        assert updated_session.message_count == 1
        assert updated_session.total_turns == 1

    async def test_is_user_allowed(self, storage):
        """Test checking user permissions."""
        # Create allowed user
        await storage.get_or_create_user(12348, "alloweduser")
        await storage.users.set_user_allowed(12348, True)

        # Check permission
        assert await storage.is_user_allowed(12348)

        # Create disallowed user
        await storage.get_or_create_user(12349, "disalloweduser")
        assert not await storage.is_user_allowed(12349)

    async def test_get_user_session_summary(self, storage):
        """Test getting user session summary."""
        # Setup user and sessions
        await storage.get_or_create_user(12350, "summaryuser")

        # Create multiple sessions
        for i in range(3):
            await storage.create_session(12350, f"/test/project{i}", f"session-{i}")

            # Add some activity
            claude_response = ClaudeResponse(
                content=f"Response {i}",
                session_id=f"session-{i}",
                cost=0.1,
                duration_ms=1000,
                num_turns=1,
            )

            await storage.save_claude_interaction(
                user_id=12350,
                session_id=f"session-{i}",
                prompt=f"Prompt {i}",
                response=claude_response,
            )

        # Get summary
        summary = await storage.get_user_session_summary(12350)
        assert summary["total_sessions"] == 3
        assert summary["active_sessions"] == 3
        assert (
            abs(summary["total_cost"] - 0.3) < 0.0001
        )  # Handle floating point precision
        assert summary["total_messages"] == 3
        assert len(summary["projects"]) == 3

    async def test_get_session_history(self, storage):
        """Test getting session history."""
        # Setup user and session
        await storage.get_or_create_user(12351, "historyuser")
        await storage.create_session(12351, "/test/history", "history-session")

        # Add some messages
        for i in range(2):
            claude_response = ClaudeResponse(
                content=f"Response {i}",
                session_id="history-session",
                cost=0.05,
                duration_ms=1000,
                num_turns=1,
                tools_used=[{"name": "Read", "input": {}}] if i == 0 else [],
            )

            await storage.save_claude_interaction(
                user_id=12351,
                session_id="history-session",
                prompt=f"Prompt {i}",
                response=claude_response,
            )

        # Get history
        history = await storage.get_session_history("history-session")
        assert history is not None
        assert len(history["messages"]) == 2
        assert len(history["tool_usage"]) == 1  # Only first message had tools
        assert history["session"]["session_id"] == "history-session"

    async def test_log_security_event(self, storage):
        """Test logging security events."""
        # Setup user
        await storage.get_or_create_user(12352, "securityuser")

        # Log security event
        await storage.log_security_event(
            user_id=12352,
            event_type="authentication_failure",
            event_data={"reason": "invalid_token"},
            success=False,
            ip_address="192.168.1.1",
        )

        # Verify event was logged
        audit_logs = await storage.audit.get_user_audit_log(12352)
        assert len(audit_logs) == 1
        assert audit_logs[0].event_type == "authentication_failure"
        assert not audit_logs[0].success
        assert audit_logs[0].event_data["reason"] == "invalid_token"

    async def test_cleanup_old_data(self, storage):
        """Test cleaning up old data."""
        # Setup user and old session
        await storage.get_or_create_user(12353, "cleanupuser")
        await storage.create_session(12353, "/test/cleanup", "cleanup-session")

        # Manually set old timestamp in database
        async with storage.db_manager.get_connection() as conn:
            await conn.execute(
                "UPDATE sessions SET last_used = datetime('now', '-35 days') "
                "WHERE session_id = ?",
                ("cleanup-session",),
            )
            await conn.commit()

        # Cleanup old data
        result = await storage.cleanup_old_data(days=30)
        assert result["sessions_cleaned"] == 1

        # Verify session is inactive
        session = await storage.sessions.get_session("cleanup-session")
        assert not session.is_active

    async def test_get_user_dashboard(self, storage):
        """Test getting user dashboard data."""
        # Setup user with activity
        await storage.get_or_create_user(12354, "dashboarduser")
        await storage.create_session(12354, "/test/dashboard", "dashboard-session")

        # Add some activity
        claude_response = ClaudeResponse(
            content="Dashboard response",
            session_id="dashboard-session",
            cost=0.1,
            duration_ms=1000,
            num_turns=1,
        )

        await storage.save_claude_interaction(
            user_id=12354,
            session_id="dashboard-session",
            prompt="Dashboard prompt",
            response=claude_response,
        )

        # Get dashboard
        dashboard = await storage.get_user_dashboard(12354)
        assert dashboard is not None
        assert dashboard["user"]["user_id"] == 12354
        assert len(dashboard["recent_sessions"]) == 1
        assert len(dashboard["recent_messages"]) == 1
        assert dashboard["stats"]["summary"]["total_cost"] == 0.1

    async def test_get_admin_dashboard(self, storage):
        """Test getting admin dashboard data."""
        # Setup some test data
        await storage.get_or_create_user(12355, "adminuser")
        await storage.create_session(12355, "/test/admin", "admin-session")

        claude_response = ClaudeResponse(
            content="Admin response",
            session_id="admin-session",
            cost=0.1,
            duration_ms=1000,
            num_turns=1,
        )

        await storage.save_claude_interaction(
            user_id=12355,
            session_id="admin-session",
            prompt="Admin prompt",
            response=claude_response,
        )

        # Get admin dashboard
        dashboard = await storage.get_admin_dashboard()
        assert dashboard is not None
        assert "system_stats" in dashboard
        assert "users" in dashboard
        assert len(dashboard["users"]) >= 1
        assert dashboard["system_stats"]["overall"]["total_users"] >= 1
