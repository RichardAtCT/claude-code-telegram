"""Tests for database management."""

import tempfile
from pathlib import Path

import pytest

from src.storage.database import DatabaseManager


@pytest.fixture
async def db_manager():
    """Create test database manager."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        manager = DatabaseManager(f"sqlite:///{db_path}")
        await manager.initialize()
        yield manager
        await manager.close()


class TestDatabaseManager:
    """Test database manager functionality."""

    async def test_initialization(self, db_manager):
        """Test database initialization."""
        # Database should be initialized
        assert await db_manager.health_check()

    async def test_connection_pool(self, db_manager):
        """Test connection pooling."""
        # Should be able to get multiple connections
        async with db_manager.get_connection() as conn1:
            async with db_manager.get_connection() as conn2:
                # Both connections should work
                await conn1.execute("SELECT 1")
                await conn2.execute("SELECT 1")

    async def test_schema_creation(self, db_manager):
        """Test that schema is created properly."""
        async with db_manager.get_connection() as conn:
            # Check that tables exist
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in await cursor.fetchall()]

            expected_tables = [
                "users",
                "sessions",
                "messages",
                "tool_usage",
                "audit_log",
                "user_tokens",
                "cost_tracking",
                "project_threads",
                "schema_version",
            ]

            for table in expected_tables:
                assert table in tables

    async def test_foreign_keys_enabled(self, db_manager):
        """Test that foreign keys are enabled."""
        async with db_manager.get_connection() as conn:
            cursor = await conn.execute("PRAGMA foreign_keys")
            result = await cursor.fetchone()
            assert result[0] == 1  # Foreign keys enabled

    async def test_indexes_created(self, db_manager):
        """Test that indexes are created."""
        async with db_manager.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name LIKE 'idx_%'"
            )
            indexes = [row[0] for row in await cursor.fetchall()]

            expected_indexes = [
                "idx_sessions_user_id",
                "idx_sessions_project_path",
                "idx_messages_session_id",
                "idx_messages_timestamp",
                "idx_audit_log_user_id",
                "idx_audit_log_timestamp",
                "idx_cost_tracking_user_date",
                "idx_project_threads_chat_active",
                "idx_project_threads_slug",
            ]

            for index in expected_indexes:
                assert index in indexes

    async def test_migration_tracking(self, db_manager):
        """Test that migrations are tracked."""
        async with db_manager.get_connection() as conn:
            cursor = await conn.execute("SELECT MAX(version) FROM schema_version")
            version = await cursor.fetchone()
            assert version[0] >= 1  # At least initial migration


async def test_migration_5_creates_conversation_summaries(db_manager):
    """Migration 5 creates conversation_summaries table, columns and indexes."""
    async with db_manager.get_connection() as conn:
        cursor = await conn.execute("PRAGMA table_info(conversation_summaries)")
        column_rows = await cursor.fetchall()
        columns = [row[1] for row in column_rows]
        assert columns == [
            "id",
            "topic_key",
            "session_id",
            "summary_text",
            "messages_included",
            "tokens_before",
            "tokens_after",
            "created_at",
        ]
        session_id_column = next(row for row in column_rows if row[1] == "session_id")
        assert session_id_column[3] == 0

        cursor = await conn.execute("PRAGMA foreign_key_list(conversation_summaries)")
        foreign_keys = await cursor.fetchall()
        assert any(
            row[2] == "sessions"
            and row[3] == "session_id"
            and row[4] == "session_id"
            for row in foreign_keys
        )

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='conversation_summaries'"
        )
        indexes = {row[0] for row in await cursor.fetchall()}
        assert "idx_conversation_summaries_topic_created" in indexes
        assert "idx_conversation_summaries_session" in indexes
