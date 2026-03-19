"""Tests for PersonaBuilder."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.assistant.persona import PersonaBuilder
from src.storage.models import UserMemoryModel, UserProfileModel


@pytest.fixture
def storage():
    s = MagicMock()
    s.profiles = MagicMock()
    s.memories = MagicMock()
    return s


async def test_build_returns_string(storage):
    storage.profiles.get_profile = AsyncMock(return_value=None)
    storage.memories.list_memories = AsyncMock(return_value=[])
    builder = PersonaBuilder(storage)
    result = await builder.build(user_id=1)
    assert isinstance(result, str)


async def test_build_includes_name_when_profile_set(storage):
    profile = UserProfileModel(user_id=1, name="Paulius", timezone="Europe/Vilnius")
    storage.profiles.get_profile = AsyncMock(return_value=profile)
    storage.memories.list_memories = AsyncMock(return_value=[])
    builder = PersonaBuilder(storage)
    result = await builder.build(user_id=1)
    assert "Paulius" in result


async def test_build_includes_memories(storage):
    storage.profiles.get_profile = AsyncMock(return_value=None)
    memories = [
        UserMemoryModel(user_id=1, key="hobby", value="orienteering"),
        UserMemoryModel(user_id=1, key="language", value="Lithuanian"),
    ]
    storage.memories.list_memories = AsyncMock(return_value=memories)
    builder = PersonaBuilder(storage)
    result = await builder.build(user_id=1)
    assert "orienteering" in result
    assert "Lithuanian" in result


async def test_build_includes_communication_style(storage):
    profile = UserProfileModel(user_id=1, communication_style="detailed")
    storage.profiles.get_profile = AsyncMock(return_value=profile)
    storage.memories.list_memories = AsyncMock(return_value=[])
    builder = PersonaBuilder(storage)
    result = await builder.build(user_id=1)
    assert "detailed" in result


async def test_build_empty_profile_returns_generic_prompt(storage):
    storage.profiles.get_profile = AsyncMock(return_value=None)
    storage.memories.list_memories = AsyncMock(return_value=[])
    builder = PersonaBuilder(storage)
    result = await builder.build(user_id=1)
    assert len(result) > 0
