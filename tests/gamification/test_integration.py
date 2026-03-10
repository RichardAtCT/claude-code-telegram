"""Integration test: tool_usage -> XP -> level up -> achievement."""

import tempfile
from pathlib import Path

import pytest

from src.storage.database import DatabaseManager
from src.gamification.repository import GamificationRepository
from src.gamification.service import GamificationService
from src.events.bus import EventBus
from src.events.types import ToolUsageSavedEvent


@pytest.fixture
async def setup():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        db = DatabaseManager(f"sqlite:///{db_path}")
        await db.initialize()
        async with db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, telegram_username, is_allowed) VALUES (1, 'test', 1)"
            )
            await conn.commit()

        event_bus = EventBus()
        await event_bus.start()
        repo = GamificationRepository(db)
        service = GamificationService(repo=repo, event_bus=event_bus)
        service.register()

        yield {"db": db, "event_bus": event_bus, "repo": repo, "service": service}

        await event_bus.stop()
        await db.close()


async def test_commit_awards_xp_and_creates_profile(setup):
    s = setup
    event = ToolUsageSavedEvent(
        user_id=1,
        session_id="s1",
        tool_name="Bash",
        tool_input={"command": "git commit -m 'feat: add RPG system'"},
    )
    await s["service"].on_tool_usage(event)

    profile = await s["repo"].get_profile(1)
    assert profile is not None
    assert profile.total_xp >= 30  # feat commit = 30 XP
    assert profile.current_streak >= 1


async def test_first_commit_unlocks_first_blood(setup):
    s = setup
    event = ToolUsageSavedEvent(
        user_id=1,
        session_id="s1",
        tool_name="Bash",
        tool_input={"command": "git commit -m 'feat: init'"},
    )
    await s["service"].on_tool_usage(event)

    achievements = await s["repo"].get_user_achievements(1)
    ids = {a.achievement_id for a in achievements}
    assert "first_blood" in ids
