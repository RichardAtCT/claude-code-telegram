"""Tests for security audit logging."""

from datetime import UTC, datetime, timedelta

import pytest

from src.security.audit import AuditEvent, AuditLogger, InMemoryAuditStorage


class TestAuditEvent:
    """Test audit event functionality."""

    def test_event_creation(self):
        """Test audit event creation."""
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=123,
            event_type="test_event",
            success=True,
            details={"action": "test"},
            risk_level="low",
        )

        assert event.user_id == 123
        assert event.event_type == "test_event"
        assert event.success is True
        assert event.details["action"] == "test"
        assert event.risk_level == "low"

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        timestamp = datetime.now(UTC)
        event = AuditEvent(
            timestamp=timestamp,
            user_id=123,
            event_type="test",
            success=True,
            details={"key": "value"},
        )

        event_dict = event.to_dict()

        assert event_dict["user_id"] == 123
        assert event_dict["event_type"] == "test"
        assert event_dict["success"] is True
        assert event_dict["details"]["key"] == "value"
        assert event_dict["timestamp"] == timestamp.isoformat()

    def test_event_to_json(self):
        """Test converting event to JSON."""
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=123,
            event_type="test",
            success=True,
            details={"key": "value"},
        )

        json_str = event.to_json()
        assert '"user_id": 123' in json_str
        assert '"event_type": "test"' in json_str
        assert '"success": true' in json_str


class TestInMemoryAuditStorage:
    """Test in-memory audit storage."""

    @pytest.fixture
    def storage(self):
        return InMemoryAuditStorage(max_events=100)

    async def test_store_event(self, storage):
        """Test storing audit events."""
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=123,
            event_type="test",
            success=True,
            details={},
        )

        await storage.store_event(event)

        assert len(storage.events) == 1
        assert storage.events[0] == event

    async def test_max_events_limit(self, storage):
        """Test that storage respects max events limit."""
        storage.max_events = 3

        # Store more events than limit
        for i in range(5):
            event = AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=i,
                event_type="test",
                success=True,
                details={},
            )
            await storage.store_event(event)

        # Should only keep last 3 events
        assert len(storage.events) == 3
        assert storage.events[0].user_id == 2  # First kept event
        assert storage.events[-1].user_id == 4  # Last event

    async def test_get_events_no_filter(self, storage):
        """Test getting events without filters."""
        # Store multiple events
        for i in range(3):
            event = AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=i,
                event_type=f"type_{i}",
                success=True,
                details={},
            )
            await storage.store_event(event)

        events = await storage.get_events()
        assert len(events) == 3

    async def test_get_events_with_user_filter(self, storage):
        """Test getting events filtered by user."""
        # Store events for different users
        for user_id in [123, 456, 123, 789]:
            event = AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=user_id,
                event_type="test",
                success=True,
                details={},
            )
            await storage.store_event(event)

        # Filter by user 123
        events = await storage.get_events(user_id=123)
        assert len(events) == 2
        assert all(e.user_id == 123 for e in events)

    async def test_get_events_with_type_filter(self, storage):
        """Test getting events filtered by type."""
        # Store events of different types
        for event_type in ["auth", "command", "auth", "file"]:
            event = AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=123,
                event_type=event_type,
                success=True,
                details={},
            )
            await storage.store_event(event)

        # Filter by auth events
        events = await storage.get_events(event_type="auth")
        assert len(events) == 2
        assert all(e.event_type == "auth" for e in events)

    async def test_get_events_with_time_filter(self, storage):
        """Test getting events filtered by time."""
        now = datetime.now(UTC)
        old_time = now - timedelta(hours=2)

        # Store events at different times
        old_event = AuditEvent(
            timestamp=old_time, user_id=123, event_type="old", success=True, details={}
        )
        new_event = AuditEvent(
            timestamp=now, user_id=123, event_type="new", success=True, details={}
        )

        await storage.store_event(old_event)
        await storage.store_event(new_event)

        # Filter by start time
        recent_events = await storage.get_events(start_time=now - timedelta(minutes=30))
        assert len(recent_events) == 1
        assert recent_events[0].event_type == "new"

    async def test_get_events_with_limit(self, storage):
        """Test getting events with limit."""
        # Store multiple events
        for i in range(5):
            event = AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=i,
                event_type="test",
                success=True,
                details={},
            )
            await storage.store_event(event)

        # Get with limit
        events = await storage.get_events(limit=3)
        assert len(events) == 3

    async def test_get_security_violations(self, storage):
        """Test getting security violations."""
        # Store mixed events
        normal_event = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=123,
            event_type="command",
            success=True,
            details={},
        )
        violation_event = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=456,
            event_type="security_violation",
            success=False,
            details={"violation_type": "path_traversal"},
        )

        await storage.store_event(normal_event)
        await storage.store_event(violation_event)

        violations = await storage.get_security_violations()
        assert len(violations) == 1
        assert violations[0].event_type == "security_violation"

    async def test_events_sorted_by_timestamp(self, storage):
        """Test that events are returned sorted by timestamp (newest first)."""
        # Store events with different timestamps
        times = [
            datetime.now(UTC) - timedelta(hours=2),
            datetime.now(UTC) - timedelta(hours=1),
            datetime.now(UTC),
        ]

        # Store in random order
        for i, timestamp in enumerate([times[1], times[2], times[0]]):
            event = AuditEvent(
                timestamp=timestamp,
                user_id=i,
                event_type="test",
                success=True,
                details={},
            )
            await storage.store_event(event)

        events = await storage.get_events()

        # Should be sorted newest first
        assert events[0].timestamp == times[2]  # Most recent
        assert events[1].timestamp == times[1]
        assert events[2].timestamp == times[0]  # Oldest


class TestAuditLogger:
    """Test audit logger functionality."""

    @pytest.fixture
    def storage(self):
        return InMemoryAuditStorage()

    @pytest.fixture
    def audit_logger(self, storage):
        return AuditLogger(storage)

    async def test_log_auth_attempt_success(self, audit_logger, storage):
        """Test logging successful authentication attempt."""
        await audit_logger.log_auth_attempt(
            user_id=123, success=True, method="whitelist", reason="user_in_whitelist"
        )

        events = await storage.get_events()
        assert len(events) == 1

        event = events[0]
        assert event.user_id == 123
        assert event.event_type == "auth_attempt"
        assert event.success is True
        assert event.details["method"] == "whitelist"
        assert event.risk_level == "low"

    async def test_log_auth_attempt_failure(self, audit_logger, storage):
        """Test logging failed authentication attempt."""
        await audit_logger.log_auth_attempt(
            user_id=456, success=False, method="token", reason="invalid_token"
        )

        events = await storage.get_events()
        event = events[0]

        assert event.success is False
        assert event.risk_level == "medium"  # Failed auth is higher risk
        assert event.details["reason"] == "invalid_token"

    async def test_log_session_event(self, audit_logger, storage):
        """Test logging session events."""
        await audit_logger.log_session_event(
            user_id=123,
            action="session_created",
            success=True,
            details={"provider": "whitelist"},
        )

        events = await storage.get_events()
        event = events[0]

        assert event.event_type == "session"
        assert event.details["action"] == "session_created"
        assert event.details["provider"] == "whitelist"

    async def test_log_command_execution(self, audit_logger, storage):
        """Test logging command execution."""
        await audit_logger.log_command(
            user_id=123,
            command="ls",
            args=["-la", "/home"],
            success=True,
            working_directory="/projects",
            execution_time=0.5,
            exit_code=0,
        )

        events = await storage.get_events()
        event = events[0]

        assert event.event_type == "command"
        assert event.details["command"] == "ls"
        assert event.details["args"] == ["-la", "/home"]
        assert event.details["execution_time"] == 0.5
        assert event.details["exit_code"] == 0

    async def test_log_command_risk_assessment(self, audit_logger, storage):
        """Test command risk assessment."""
        # Test high-risk command
        await audit_logger.log_command(
            user_id=123, command="rm", args=["-rf", "/tmp/test"], success=True
        )

        events = await storage.get_events()
        high_risk_event = events[0]
        assert high_risk_event.risk_level == "high"

        # Test low-risk command
        await audit_logger.log_command(
            user_id=123, command="echo", args=["hello"], success=True
        )

        events = await storage.get_events()
        low_risk_event = events[0]  # Most recent
        assert low_risk_event.risk_level == "low"

    async def test_log_file_access(self, audit_logger, storage):
        """Test logging file access."""
        await audit_logger.log_file_access(
            user_id=123,
            file_path="/projects/file.txt",
            action="read",
            success=True,
            file_size=1024,
        )

        events = await storage.get_events()
        event = events[0]

        assert event.event_type == "file_access"
        assert event.details["file_path"] == "/projects/file.txt"
        assert event.details["action"] == "read"
        assert event.details["file_size"] == 1024

    async def test_log_file_access_risk_assessment(self, audit_logger, storage):
        """Test file access risk assessment."""
        # High-risk: delete sensitive file
        await audit_logger.log_file_access(
            user_id=123, file_path="/etc/passwd", action="delete", success=True
        )

        events = await storage.get_events()
        high_risk_event = events[0]
        assert high_risk_event.risk_level == "high"

        # Low-risk: read normal file
        await audit_logger.log_file_access(
            user_id=123, file_path="/projects/readme.txt", action="read", success=True
        )

        events = await storage.get_events()
        low_risk_event = events[0]  # Most recent
        assert low_risk_event.risk_level == "low"

    async def test_log_security_violation(self, audit_logger, storage):
        """Test logging security violations."""
        await audit_logger.log_security_violation(
            user_id=123,
            violation_type="path_traversal",
            details="Attempted to access ../../../etc/passwd",
            severity="high",
            attempted_action="file_read",
        )

        events = await storage.get_events()
        event = events[0]

        assert event.event_type == "security_violation"
        assert event.success is False  # Violations are always failures
        assert event.details["violation_type"] == "path_traversal"
        assert event.details["severity"] == "high"
        assert event.risk_level == "critical"  # High severity maps to critical risk

    async def test_log_rate_limit_exceeded(self, audit_logger, storage):
        """Test logging rate limit exceeded."""
        await audit_logger.log_rate_limit_exceeded(
            user_id=123, limit_type="request", current_usage=15.0, limit_value=10.0
        )

        events = await storage.get_events()
        event = events[0]

        assert event.event_type == "rate_limit_exceeded"
        assert event.success is False
        assert event.details["limit_type"] == "request"
        assert event.details["current_usage"] == 15.0
        assert event.details["utilization"] == 1.5

    async def test_get_user_activity_summary(self, audit_logger, storage):
        """Test getting user activity summary."""
        user_id = 123

        # Create various events for user
        await audit_logger.log_auth_attempt(user_id, True, "whitelist")
        await audit_logger.log_command(user_id, "ls", [], True)
        await audit_logger.log_security_violation(user_id, "test", "test", "medium")
        await audit_logger.log_command(user_id, "echo", [], False)

        summary = await audit_logger.get_user_activity_summary(user_id, hours=24)

        assert summary["user_id"] == user_id
        assert summary["total_events"] == 4
        assert summary["security_violations"] == 1
        assert (
            summary["success_rate"] == 0.5
        )  # 2 successful out of 4 (violation is unsuccessful)
        assert "auth_attempt" in summary["event_types"]
        assert "command" in summary["event_types"]
        assert summary["event_types"]["command"] == 2

    async def test_get_security_dashboard(self, audit_logger, storage):
        """Test getting security dashboard."""
        # Create various events
        await audit_logger.log_auth_attempt(123, False, "token", "invalid")
        await audit_logger.log_auth_attempt(456, True, "whitelist")
        await audit_logger.log_security_violation(123, "path_traversal", "test", "high")
        await audit_logger.log_security_violation(456, "injection", "test", "medium")

        dashboard = await audit_logger.get_security_dashboard()

        assert dashboard["total_events"] == 4
        assert dashboard["security_violations"] == 2
        assert dashboard["authentication_failures"] == 1
        assert dashboard["active_users"] == 2
        assert "path_traversal" in dashboard["top_violation_types"]
        assert "injection" in dashboard["top_violation_types"]
