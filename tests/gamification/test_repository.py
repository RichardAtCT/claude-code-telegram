"""Tests for GamificationRepository."""

import tempfile
from pathlib import Path

import pytest

from src.storage.database import DatabaseManager
from src.gamification.repository import GamificationRepository
from src.gamification.models import RpgProfile, XpLogEntry, Achievement


@pytest.fixture
async def db():
    """Create file-based test database with all migrations."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        manager = DatabaseManager(f"sqlite:///{db_path}")
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.fixture
async def repo(db):
    return GamificationRepository(db)


@pytest.fixture
async def seeded_db(db):
    """DB with a test user."""
    async with db.get_connection() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, telegram_username, is_allowed) VALUES (1, 'test', 1)"
        )
        await conn.commit()
    return db


@pytest.mark.asyncio
class TestGetProfile:
    async def test_returns_none_for_missing_user(self, repo):
        assert await repo.get_profile(999) is None

    async def test_returns_profile_after_creation(self, repo, seeded_db):
        await repo.create_profile(1)
        profile = await repo.get_profile(1)
        assert profile is not None
        assert profile.user_id == 1
        assert profile.level == 1


@pytest.mark.asyncio
class TestUpdateProfile:
    async def test_updates_xp_and_level(self, repo, seeded_db):
        await repo.create_profile(1)
        await repo.update_profile(1, total_xp=500, level=3, str_points=10)
        profile = await repo.get_profile(1)
        assert profile.total_xp == 500
        assert profile.level == 3
        assert profile.str_points == 10


@pytest.mark.asyncio
class TestXpLog:
    async def test_add_and_retrieve(self, repo, seeded_db):
        await repo.create_profile(1)
        entry = XpLogEntry(user_id=1, xp_amount=10, source="commit", stat_type="str")
        await repo.add_xp_log(entry)
        history = await repo.get_xp_history(1, limit=10)
        assert len(history) == 1
        assert history[0].xp_amount == 10


@pytest.mark.asyncio
class TestAchievements:
    async def test_get_active_definitions(self, repo, seeded_db):
        definitions = await repo.get_active_definitions()
        assert len(definitions) == 17  # 17 seeded

    async def test_unlock_and_retrieve(self, repo, seeded_db):
        await repo.create_profile(1)
        ach = Achievement(user_id=1, achievement_id="first_blood")
        await repo.unlock_achievement(ach)
        unlocked = await repo.get_user_achievements(1)
        assert len(unlocked) == 1
        assert unlocked[0].achievement_id == "first_blood"

    async def test_no_duplicate_unlock(self, repo, seeded_db):
        await repo.create_profile(1)
        ach = Achievement(user_id=1, achievement_id="first_blood")
        await repo.unlock_achievement(ach)
        await repo.unlock_achievement(ach)  # should not raise
        unlocked = await repo.get_user_achievements(1)
        assert len(unlocked) == 1
