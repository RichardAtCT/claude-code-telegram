"""Integration tests for the storage layer.

Exercises the real SQLite database through the DatabaseManager,
verifying user creation, session lifecycle, cost tracking and
analytics views.
"""

from datetime import datetime, UTC

import pytest

from src.storage.database import DatabaseManager


class TestCreateUserAndQuery:
    """Create users via SQL and verify retrieval."""

    async def test_create_user_and_query(self, in_memory_db: DatabaseManager):
        user_id = 42
        username = "alice"

        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username, is_allowed) "
                "VALUES (?, ?, ?)",
                (user_id, username, True),
            )
            await conn.commit()

        async with in_memory_db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT user_id, telegram_username, is_allowed "
                "FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()

        assert row is not None
        row_dict = dict(row)
        assert row_dict["user_id"] == user_id
        assert row_dict["telegram_username"] == username
        assert row_dict["is_allowed"] == 1

    async def test_query_nonexistent_user(self, in_memory_db: DatabaseManager):
        async with in_memory_db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (99999,)
            )
            row = await cursor.fetchone()

        assert row is None


class TestSessionLifecycle:
    """Create sessions, add messages, query, and close."""

    async def _insert_user(self, db: DatabaseManager, user_id: int) -> None:
        async with db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username) VALUES (?, ?)",
                (user_id, "testuser"),
            )
            await conn.commit()

    async def test_session_lifecycle(self, in_memory_db: DatabaseManager):
        user_id = 100
        session_id = "sess-001"
        await self._insert_user(in_memory_db, user_id)

        # Create session
        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO sessions (session_id, user_id, project_path) "
                "VALUES (?, ?, ?)",
                (session_id, user_id, "/tmp/project"),
            )
            await conn.commit()

        # Add messages
        async with in_memory_db.get_connection() as conn:
            for i in range(3):
                await conn.execute(
                    "INSERT INTO messages (session_id, user_id, prompt, response, cost) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, user_id, f"prompt_{i}", f"response_{i}", 0.01),
                )
            await conn.commit()

        # Query messages
        async with in_memory_db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            assert dict(row)["cnt"] == 3

        # Close session
        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "UPDATE sessions SET is_active = FALSE WHERE session_id = ?",
                (session_id,),
            )
            await conn.commit()

        async with in_memory_db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT is_active FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            assert dict(row)["is_active"] == 0


class TestCostTracking:
    """Record costs and verify per-user totals."""

    async def test_cost_tracking(self, in_memory_db: DatabaseManager):
        user_id = 200
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username) VALUES (?, ?)",
                (user_id, "costuser"),
            )
            await conn.commit()

        # Record multiple costs
        costs = [0.05, 0.10, 0.15]
        async with in_memory_db.get_connection() as conn:
            for cost in costs:
                await conn.execute(
                    "INSERT INTO cost_tracking (user_id, date, daily_cost, request_count) "
                    "VALUES (?, ?, ?, 1) "
                    "ON CONFLICT(user_id, date) DO UPDATE SET "
                    "daily_cost = daily_cost + excluded.daily_cost, "
                    "request_count = request_count + 1",
                    (user_id, today, cost),
                )
            await conn.commit()

        # Verify totals
        async with in_memory_db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT daily_cost, request_count FROM cost_tracking "
                "WHERE user_id = ? AND date = ?",
                (user_id, today),
            )
            row = await cursor.fetchone()

        row_dict = dict(row)
        assert abs(row_dict["daily_cost"] - sum(costs)) < 1e-9
        assert row_dict["request_count"] == len(costs)


class TestAnalyticsStats:
    """Populate data and verify analytics views."""

    async def test_analytics_stats(self, in_memory_db: DatabaseManager):
        user_id = 300
        session_id = "sess-analytics"

        async with in_memory_db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username) VALUES (?, ?)",
                (user_id, "analytics_user"),
            )
            await conn.execute(
                "INSERT INTO sessions (session_id, user_id, project_path) "
                "VALUES (?, ?, ?)",
                (session_id, user_id, "/tmp/analytics"),
            )
            for i in range(5):
                await conn.execute(
                    "INSERT INTO messages "
                    "(session_id, user_id, prompt, response, cost, duration_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, user_id, f"p{i}", f"r{i}", 0.02, 100 + i * 10),
                )
            await conn.commit()

        # Query the daily_stats view
        async with in_memory_db.get_connection() as conn:
            cursor = await conn.execute("SELECT * FROM daily_stats")
            rows = await cursor.fetchall()

        assert len(rows) >= 1
        day = dict(rows[0])
        assert day["active_users"] == 1
        assert day["total_messages"] == 5
        assert abs(day["total_cost"] - 0.10) < 1e-9

        # Query the user_stats view
        async with in_memory_db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM user_stats WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()

        row_dict = dict(row)
        assert row_dict["total_sessions"] == 1
        assert row_dict["total_messages"] == 5
