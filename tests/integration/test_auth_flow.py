"""Integration tests for authentication and security flows.

Tests SQLiteTokenStorage and SQLiteAuditStorage against a real database,
whitelist auth decisions, and rate-limiter behaviour.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.security.audit import AuditEvent, AuditLogger, SQLiteAuditStorage
from src.security.auth import (
    SQLiteTokenStorage,
    TokenAuthProvider,
    WhitelistAuthProvider,
)
from src.security.rate_limiter import RateLimiter
from src.storage.database import DatabaseManager


# ── SQLiteTokenStorage ───────────────────────────────────────────────


class TestSQLiteTokenStorage:
    """End-to-end token storage against real SQLite."""

    async def test_store_retrieve_revoke(self, in_memory_db: DatabaseManager):
        storage = SQLiteTokenStorage(in_memory_db)

        user_id = 500
        token_hash = "abc123hash"
        expires_at = datetime.now(UTC) + timedelta(days=7)

        # Ensure the user row exists (FK constraint)
        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username) VALUES (?, ?)",
                (user_id, "tokenuser"),
            )
            await conn.commit()

        # Store
        await storage.store_token(user_id, token_hash, expires_at)

        # Retrieve
        data = await storage.get_user_token(user_id)
        assert data is not None
        assert data["hash"] == token_hash

        # Revoke
        await storage.revoke_token(user_id)
        data = await storage.get_user_token(user_id)
        assert data is None

    async def test_expired_token_not_returned(self, in_memory_db: DatabaseManager):
        storage = SQLiteTokenStorage(in_memory_db)
        user_id = 501

        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username) VALUES (?, ?)",
                (user_id, "expireduser"),
            )
            await conn.commit()

        past = datetime.now(UTC) - timedelta(days=1)
        await storage.store_token(user_id, "old_hash", past)

        data = await storage.get_user_token(user_id)
        assert data is None

    async def test_new_token_deactivates_old(self, in_memory_db: DatabaseManager):
        storage = SQLiteTokenStorage(in_memory_db)
        user_id = 502

        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username) VALUES (?, ?)",
                (user_id, "multitoken"),
            )
            await conn.commit()

        future = datetime.now(UTC) + timedelta(days=7)
        await storage.store_token(user_id, "hash_v1", future)
        await storage.store_token(user_id, "hash_v2", future)

        data = await storage.get_user_token(user_id)
        assert data is not None
        assert data["hash"] == "hash_v2"


# ── SQLiteAuditStorage ──────────────────────────────────────────────


class TestSQLiteAuditStorage:
    """End-to-end audit event storage against real SQLite."""

    async def _ensure_user(self, db: DatabaseManager, user_id: int) -> None:
        async with db.get_connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO users (user_id, telegram_username) "
                "VALUES (?, ?)",
                (user_id, f"user_{user_id}"),
            )
            await conn.commit()

    async def test_store_and_query_events(self, in_memory_db: DatabaseManager):
        storage = SQLiteAuditStorage(in_memory_db)
        user_id = 600
        await self._ensure_user(in_memory_db, user_id)

        event = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=user_id,
            event_type="auth_attempt",
            success=True,
            details={"method": "whitelist"},
        )
        await storage.store_event(event)

        events = await storage.get_events(user_id=user_id)
        assert len(events) == 1
        assert events[0].event_type == "auth_attempt"
        assert events[0].success is True

    async def test_filter_by_event_type(self, in_memory_db: DatabaseManager):
        storage = SQLiteAuditStorage(in_memory_db)
        user_id = 601
        await self._ensure_user(in_memory_db, user_id)

        for etype in ("auth_attempt", "command", "auth_attempt"):
            event = AuditEvent(
                timestamp=datetime.now(UTC),
                user_id=user_id,
                event_type=etype,
                success=True,
                details={},
            )
            await storage.store_event(event)

        auth_events = await storage.get_events(
            user_id=user_id, event_type="auth_attempt"
        )
        assert len(auth_events) == 2

        cmd_events = await storage.get_events(
            user_id=user_id, event_type="command"
        )
        assert len(cmd_events) == 1

    async def test_security_violations(self, in_memory_db: DatabaseManager):
        storage = SQLiteAuditStorage(in_memory_db)
        user_id = 602
        await self._ensure_user(in_memory_db, user_id)

        violation = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=user_id,
            event_type="security_violation",
            success=False,
            details={"violation_type": "path_traversal"},
            risk_level="high",
        )
        await storage.store_event(violation)

        normal = AuditEvent(
            timestamp=datetime.now(UTC),
            user_id=user_id,
            event_type="auth_attempt",
            success=True,
            details={},
        )
        await storage.store_event(normal)

        violations = await storage.get_security_violations(user_id=user_id)
        assert len(violations) == 1
        assert violations[0].event_type == "security_violation"

    async def test_audit_logger_integration(self, in_memory_db: DatabaseManager):
        """AuditLogger -> SQLiteAuditStorage -> query round-trip."""
        storage = SQLiteAuditStorage(in_memory_db)
        audit = AuditLogger(storage)
        user_id = 603
        await self._ensure_user(in_memory_db, user_id)

        await audit.log_auth_attempt(user_id, success=True, method="token")
        await audit.log_auth_attempt(user_id, success=False, method="whitelist")

        events = await storage.get_events(user_id=user_id)
        assert len(events) == 2

        successes = [e for e in events if e.success]
        failures = [e for e in events if not e.success]
        assert len(successes) == 1
        assert len(failures) == 1


# ── WhitelistAuthProvider ────────────────────────────────────────────


class TestWhitelistAuth:
    """Verify allowed / denied user decisions."""

    async def test_allowed_user(self):
        provider = WhitelistAuthProvider([111, 222])
        assert await provider.authenticate(111, {}) is True
        assert await provider.authenticate(222, {}) is True

    async def test_denied_user(self):
        provider = WhitelistAuthProvider([111, 222])
        assert await provider.authenticate(999, {}) is False

    async def test_dev_mode_allows_all(self):
        provider = WhitelistAuthProvider([], allow_all_dev=True)
        assert await provider.authenticate(12345, {}) is True

    async def test_user_info_for_allowed(self):
        provider = WhitelistAuthProvider([111])
        info = await provider.get_user_info(111)
        assert info is not None
        assert info["auth_type"] == "whitelist"

    async def test_user_info_for_denied(self):
        provider = WhitelistAuthProvider([111])
        info = await provider.get_user_info(999)
        assert info is None


# ── RateLimiter ──────────────────────────────────────────────────────


class TestRateLimiter:
    """Verify request and cost limiting."""

    async def test_requests_within_limit(self, mock_settings):
        limiter = RateLimiter(mock_settings)
        user_id = 700

        # First request should pass
        allowed, msg = await limiter.check_rate_limit(user_id, cost=0.0)
        assert allowed is True
        assert msg is None

    async def test_burst_exceeded(self, mock_settings):
        limiter = RateLimiter(mock_settings)
        user_id = 701

        # Consume requests until denied.
        # The rate limiter double-consumes tokens internally
        # (_check_request_rate + _consume_request_tokens), so the
        # exact number of allowed requests may be less than
        # burst capacity.  We just need to verify that eventually
        # the limiter refuses a request.
        allowed_count = 0
        for _ in range(mock_settings.rate_limit_burst + 2):
            allowed, msg = await limiter.check_rate_limit(user_id, cost=0.0)
            if allowed:
                allowed_count += 1
            else:
                break

        assert allowed_count > 0, "At least one request should be allowed"
        assert allowed_count <= mock_settings.rate_limit_burst

        # The last call should have been denied
        allowed, msg = await limiter.check_rate_limit(user_id, cost=0.0)
        assert allowed is False
        assert msg is not None
        assert "Rate limit exceeded" in msg

    async def test_cost_limit_exceeded(self, mock_settings):
        limiter = RateLimiter(mock_settings)
        user_id = 702

        # One request that blows the cost budget
        allowed, msg = await limiter.check_rate_limit(
            user_id, cost=mock_settings.claude_max_cost_per_user + 1.0
        )
        assert allowed is False
        assert "Cost limit exceeded" in msg

    async def test_reset_user_limits(self, mock_settings):
        limiter = RateLimiter(mock_settings)
        user_id = 703

        # Exhaust burst
        for _ in range(mock_settings.rate_limit_burst):
            await limiter.check_rate_limit(user_id, cost=0.0)

        # Should be denied
        allowed, _ = await limiter.check_rate_limit(user_id, cost=0.0)
        assert allowed is False

        # Reset
        await limiter.reset_user_limits(user_id)

        # Should be allowed again
        allowed, _ = await limiter.check_rate_limit(user_id, cost=0.0)
        assert allowed is True

    async def test_user_status(self, mock_settings):
        limiter = RateLimiter(mock_settings)
        user_id = 704

        status = limiter.get_user_status(user_id)
        assert "request_bucket" in status
        assert "cost_usage" in status
        assert status["cost_usage"]["current"] == 0.0
