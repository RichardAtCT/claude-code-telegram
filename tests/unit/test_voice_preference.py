"""Tests for voice response preference storage."""

import pytest

from src.storage.database import DatabaseManager
from src.storage.models import UserModel
from src.storage.repositories import UserRepository


@pytest.fixture
async def db_manager(tmp_path):
    """Create an in-memory database manager."""
    db_path = str(tmp_path / "test.db")
    manager = DatabaseManager(f"sqlite:///{db_path}")
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def user_repo(db_manager):
    """Create a UserRepository with initialized DB."""
    return UserRepository(db_manager)


async def test_get_voice_responses_default_false(user_repo):
    """New users have voice_responses_enabled = False by default."""
    user = UserModel(user_id=123, telegram_username="testuser")
    await user_repo.create_user(user)
    result = await user_repo.get_voice_responses_enabled(123)
    assert result is False


async def test_set_voice_responses_enabled(user_repo):
    """Setting voice_responses_enabled to True persists."""
    user = UserModel(user_id=456, telegram_username="testuser2")
    await user_repo.create_user(user)
    await user_repo.set_voice_responses_enabled(456, True)
    result = await user_repo.get_voice_responses_enabled(456)
    assert result is True


async def test_set_voice_responses_disabled(user_repo):
    """Setting voice_responses_enabled back to False persists."""
    user = UserModel(user_id=789, telegram_username="testuser3")
    await user_repo.create_user(user)
    await user_repo.set_voice_responses_enabled(789, True)
    await user_repo.set_voice_responses_enabled(789, False)
    result = await user_repo.get_voice_responses_enabled(789)
    assert result is False


async def test_get_voice_responses_nonexistent_user(user_repo):
    """Nonexistent user returns False."""
    result = await user_repo.get_voice_responses_enabled(999)
    assert result is False
