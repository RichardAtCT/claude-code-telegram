"""Tests for BriefingAssembler."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.assistant.briefing import BriefingAssembler
from src.storage.models import TaskModel, UserMemoryModel, UserProfileModel


@pytest.fixture
def storage():
    s = MagicMock()
    s.profiles = MagicMock()
    s.memories = MagicMock()
    s.tasks = MagicMock()
    return s


async def test_briefing_includes_greeting_with_name(storage):
    storage.profiles.get_profile = AsyncMock(
        return_value=UserProfileModel(user_id=1, name="Paulius")
    )
    storage.memories.list_memories = AsyncMock(return_value=[])
    storage.tasks.list_tasks = AsyncMock(return_value=[])

    assembler = BriefingAssembler(storage)
    result = await assembler.build(user_id=1)
    assert "Paulius" in result


async def test_briefing_includes_open_tasks(storage):
    storage.profiles.get_profile = AsyncMock(return_value=None)
    storage.memories.list_memories = AsyncMock(return_value=[])
    storage.tasks.list_tasks = AsyncMock(return_value=[
        TaskModel(id=1, user_id=1, title="Buy groceries", status="open"),
        TaskModel(id=2, user_id=1, title="Call dentist", status="open"),
    ])

    assembler = BriefingAssembler(storage)
    result = await assembler.build(user_id=1)
    assert "Buy groceries" in result
    assert "Call dentist" in result


async def test_briefing_no_tasks_says_clear(storage):
    storage.profiles.get_profile = AsyncMock(return_value=None)
    storage.memories.list_memories = AsyncMock(return_value=[])
    storage.tasks.list_tasks = AsyncMock(return_value=[])

    assembler = BriefingAssembler(storage)
    result = await assembler.build(user_id=1)
    assert "no open tasks" in result.lower() or "clear" in result.lower() or "0" in result


async def test_briefing_includes_memories(storage):
    storage.profiles.get_profile = AsyncMock(return_value=None)
    storage.memories.list_memories = AsyncMock(return_value=[
        UserMemoryModel(id=1, user_id=1, key="focus_area", value="deep work"),
    ])
    storage.tasks.list_tasks = AsyncMock(return_value=[])

    assembler = BriefingAssembler(storage)
    result = await assembler.build(user_id=1)
    assert "deep work" in result


async def test_briefing_always_returns_string(storage):
    storage.profiles.get_profile = AsyncMock(return_value=None)
    storage.memories.list_memories = AsyncMock(return_value=[])
    storage.tasks.list_tasks = AsyncMock(return_value=[])

    assembler = BriefingAssembler(storage)
    result = await assembler.build(user_id=1)
    assert isinstance(result, str)
    assert len(result) > 0
