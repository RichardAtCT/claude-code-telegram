"""Tests for personal assistant repositories."""
import tempfile
from pathlib import Path

import pytest

from src.storage.database import DatabaseManager
from src.storage.models import TaskModel, UserMemoryModel, UserProfileModel
from src.storage.repositories import (
    TaskRepository,
    UserMemoryRepository,
    UserProfileRepository,
)


@pytest.fixture
async def db_manager():
    with tempfile.TemporaryDirectory() as tmp:
        db = DatabaseManager(f"sqlite:///{Path(tmp)}/test.db")
        await db.initialize()
        # Seed a user
        async with db.get_connection() as conn:
            await conn.execute("INSERT INTO users (user_id, is_allowed) VALUES (42, 1)")
            await conn.commit()
        yield db
        await db.close()


# --- UserProfileRepository ---

async def test_get_profile_returns_none_when_missing(db_manager):
    repo = UserProfileRepository(db_manager)
    result = await repo.get_profile(42)
    assert result is None


async def test_upsert_and_get_profile(db_manager):
    repo = UserProfileRepository(db_manager)
    profile = UserProfileModel(user_id=42, name="Paulius", timezone="Europe/Vilnius")
    await repo.upsert_profile(profile)
    result = await repo.get_profile(42)
    assert result is not None
    assert result.name == "Paulius"
    assert result.timezone == "Europe/Vilnius"


async def test_upsert_profile_updates_existing(db_manager):
    repo = UserProfileRepository(db_manager)
    await repo.upsert_profile(UserProfileModel(user_id=42, name="Old"))
    await repo.upsert_profile(UserProfileModel(user_id=42, name="New"))
    result = await repo.get_profile(42)
    assert result.name == "New"


# --- UserMemoryRepository ---

async def test_set_and_get_memory(db_manager):
    repo = UserMemoryRepository(db_manager)
    await repo.set_memory(42, "preferred_language", "Python")
    memories = await repo.list_memories(42)
    assert any(m.key == "preferred_language" and m.value == "Python" for m in memories)


async def test_set_memory_overwrites_same_key(db_manager):
    repo = UserMemoryRepository(db_manager)
    await repo.set_memory(42, "language", "Python")
    await repo.set_memory(42, "language", "Go")
    memories = await repo.list_memories(42)
    lang_memories = [m for m in memories if m.key == "language"]
    assert len(lang_memories) == 1
    assert lang_memories[0].value == "Go"


async def test_delete_memory(db_manager):
    repo = UserMemoryRepository(db_manager)
    await repo.set_memory(42, "to_delete", "value")
    memories = await repo.list_memories(42)
    mem_id = memories[0].id
    deleted = await repo.delete_memory(42, mem_id)
    assert deleted is True
    memories_after = await repo.list_memories(42)
    assert len(memories_after) == 0


# --- TaskRepository ---

async def test_create_and_list_tasks(db_manager):
    repo = TaskRepository(db_manager)
    task = TaskModel(user_id=42, title="Write tests")
    created = await repo.create_task(task)
    assert created.id is not None
    tasks = await repo.list_tasks(42)
    assert any(t.title == "Write tests" for t in tasks)


async def test_list_tasks_filters_by_status(db_manager):
    repo = TaskRepository(db_manager)
    await repo.create_task(TaskModel(user_id=42, title="Open task", status="open"))
    await repo.create_task(TaskModel(user_id=42, title="Done task", status="done"))
    open_tasks = await repo.list_tasks(42, status="open")
    assert all(t.status == "open" for t in open_tasks)
    assert len(open_tasks) == 1


async def test_update_task_status(db_manager):
    repo = TaskRepository(db_manager)
    task = await repo.create_task(TaskModel(user_id=42, title="Buy milk"))
    updated = await repo.update_task_status(task.id, "done")
    assert updated is True
    tasks = await repo.list_tasks(42, status="done")
    assert any(t.title == "Buy milk" for t in tasks)


async def test_delete_task(db_manager):
    repo = TaskRepository(db_manager)
    task = await repo.create_task(TaskModel(user_id=42, title="Temp task"))
    deleted = await repo.delete_task(42, task.id)
    assert deleted is True
    tasks = await repo.list_tasks(42)
    assert not any(t.id == task.id for t in tasks)
