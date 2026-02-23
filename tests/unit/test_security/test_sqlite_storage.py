"""Tests for SQLite-backed audit and token storage."""

from datetime import UTC, datetime, timedelta

import pytest

from src.security.audit import AuditEvent, SQLiteAuditStorage
from src.security.auth import SQLiteTokenStorage
from src.storage.database import DatabaseManager


@pytest.fixture
async def db_manager(tmp_path):
    """Create an in-memory DatabaseManager with schema initialised."""
    db_url = str(tmp_path / "test.db")
    manager = DatabaseManager(db_url)
    await manager.initialize()
    return manager


class TestSQLiteAuditStorage:
    """Test SQLite-backed audit storage."""

    @pytest.fixture
    async def storage(self, db_manager):
        return SQLiteAuditStorage(db_manager)

    async def test_store_and_retrieve_event(self, storage):
        """Test round-trip store then retrieve."""
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=123,
            event_type="test_event",
            success=True,
            details={"action": "test"},
            risk_level="low",
        )
        await storage.store_event(event)

        events = await storage.get_events()
        assert len(events) == 1
        assert events[0].user_id == 123
        assert events[0].event_type == "test_event"
        assert events[0].success is True
        assert events[0].details["action"] == "test"

    async def test_filter_by_user_id(self, storage):
        """Test filtering events by user_id."""
        for uid in [100, 200, 100]:
            await storage.store_event(
                AuditEvent(
                    timestamp=datetime.now(UTC),
                    user_id=uid,
                    event_type="cmd",
                    success=True,
                    details={},
                )
            )

        events = await storage.get_events(user_id=100)
        assert len(events) == 2
        assert all(e.user_id == 100 for e in events)

    async def test_filter_by_event_type(self, storage):
        """Test filtering events by event_type."""
        for etype in ["auth", "command", "auth"]:
            await storage.store_event(
                AuditEvent(
                    timestamp=datetime.now(UTC),
                    user_id=1,
                    event_type=etype,
                    success=True,
                    details={},
                )
            )

        events = await storage.get_events(event_type="auth")
        assert len(events) == 2

    async def test_filter_by_time_range(self, storage):
        """Test filtering by start_time."""
        old = datetime.now(UTC) - timedelta(hours=2)
        now = datetime.now(UTC)

        await storage.store_event(
            AuditEvent(
                timestamp=old, user_id=1, event_type="old", success=True, details={}
            )
        )
        await storage.store_event(
            AuditEvent(
                timestamp=now, user_id=1, event_type="new", success=True, details={}
            )
        )

        events = await storage.get_events(start_time=now - timedelta(minutes=30))
        assert len(events) == 1
        assert events[0].event_type == "new"

    async def test_limit(self, storage):
        """Test that limit is respected."""
        for i in range(5):
            await storage.store_event(
                AuditEvent(
                    timestamp=datetime.now(UTC),
                    user_id=i,
                    event_type="t",
                    success=True,
                    details={},
                )
            )

        events = await storage.get_events(limit=3)
        assert len(events) == 3

    async def test_get_security_violations(self, storage):
        """Test security violations filter."""
        await storage.store_event(
            AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=1,
                event_type="command",
                success=True,
                details={},
            )
        )
        await storage.store_event(
            AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=1,
                event_type="security_violation",
                success=False,
                details={"violation_type": "path_traversal"},
            )
        )

        violations = await storage.get_security_violations()
        assert len(violations) == 1
        assert violations[0].event_type == "security_violation"

    async def test_malformed_event_data_handled(self, storage):
        """Test that malformed JSON in event_data doesn't crash."""
        # Store a valid event first
        await storage.store_event(
            AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=1,
                event_type="test",
                success=True,
                details={"key": "value"},
            )
        )

        # Manually corrupt the event_data in the DB
        async with storage.db.get_connection() as conn:
            await conn.execute(
                "UPDATE audit_log SET event_data = 'not-json' WHERE user_id = 1"
            )
            await conn.commit()

        events = await storage.get_events()
        assert len(events) == 1
        assert "raw" in events[0].details


class TestSQLiteTokenStorage:
    """Test SQLite-backed token storage."""

    @pytest.fixture
    async def storage(self, db_manager):
        return SQLiteTokenStorage(db_manager)

    async def test_store_and_retrieve_token(self, storage):
        """Test storing and retrieving a token."""
        expires = datetime.now(UTC) + timedelta(days=1)
        await storage.store_token(123, "hash_abc", expires)

        token = await storage.get_user_token(123)
        assert token is not None
        assert token["hash"] == "hash_abc"

    async def test_expired_token_returns_none(self, storage):
        """Test that expired tokens are not returned."""
        expires = datetime.now(UTC) - timedelta(days=1)
        await storage.store_token(123, "hash_old", expires)

        token = await storage.get_user_token(123)
        assert token is None

    async def test_new_token_deactivates_old(self, storage):
        """Test that storing a new token deactivates previous ones."""
        expires = datetime.now(UTC) + timedelta(days=1)
        await storage.store_token(123, "hash_first", expires)
        await storage.store_token(123, "hash_second", expires)

        token = await storage.get_user_token(123)
        assert token is not None
        assert token["hash"] == "hash_second"

    async def test_revoke_token(self, storage):
        """Test token revocation."""
        expires = datetime.now(UTC) + timedelta(days=1)
        await storage.store_token(123, "hash_abc", expires)

        await storage.revoke_token(123)

        token = await storage.get_user_token(123)
        assert token is None

    async def test_get_nonexistent_user_token(self, storage):
        """Test getting token for user with no tokens."""
        token = await storage.get_user_token(999)
        assert token is None
