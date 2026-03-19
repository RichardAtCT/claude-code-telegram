"""Tests for personal assistant models."""
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.storage.database import DatabaseManager
from src.storage.models import TaskModel, UserMemoryModel, UserProfileModel


@pytest.fixture
async def db_manager():
    with tempfile.TemporaryDirectory() as tmp:
        db = DatabaseManager(f"sqlite:///{Path(tmp)}/test.db")
        await db.initialize()
        yield db
        await db.close()


async def test_user_profile_model_from_row(db_manager):
    async with db_manager.get_connection() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, is_allowed) VALUES (1, 1)"
        )
        await conn.execute(
            "INSERT INTO user_profiles (user_id, name, timezone) VALUES (1, 'Paulius', 'Europe/Vilnius')"
        )
        await conn.commit()
        cursor = await conn.execute("SELECT * FROM user_profiles WHERE user_id = 1")
        row = await cursor.fetchone()
    profile = UserProfileModel.from_row(row)
    assert profile.user_id == 1
    assert profile.name == "Paulius"
    assert profile.timezone == "Europe/Vilnius"


async def test_user_memory_model_from_row(db_manager):
    async with db_manager.get_connection() as conn:
        await conn.execute("INSERT INTO users (user_id, is_allowed) VALUES (1, 1)")
        await conn.execute(
            "INSERT INTO user_memories (user_id, key, value) VALUES (1, 'language', 'Lithuanian')"
        )
        await conn.commit()
        cursor = await conn.execute("SELECT * FROM user_memories WHERE user_id = 1")
        row = await cursor.fetchone()
    mem = UserMemoryModel.from_row(row)
    assert mem.key == "language"
    assert mem.value == "Lithuanian"


async def test_task_model_from_row(db_manager):
    async with db_manager.get_connection() as conn:
        await conn.execute("INSERT INTO users (user_id, is_allowed) VALUES (1, 1)")
        await conn.execute(
            "INSERT INTO tasks (user_id, title, status) VALUES (1, 'Buy milk', 'open')"
        )
        await conn.commit()
        cursor = await conn.execute("SELECT * FROM tasks WHERE user_id = 1")
        row = await cursor.fetchone()
    task = TaskModel.from_row(row)
    assert task.title == "Buy milk"
    assert task.status == "open"
