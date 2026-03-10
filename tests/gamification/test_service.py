"""Tests for GamificationService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from src.gamification.service import GamificationService
from src.gamification.models import RpgProfile, AchievementDefinition
from src.events.types import ToolUsageSavedEvent, LevelUpEvent


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_profile.return_value = RpgProfile(user_id=1, total_xp=90, level=1)
    repo.get_active_definitions.return_value = [
        AchievementDefinition(
            achievement_id="first_blood", name="First Blood",
            description="First commit", condition_type="counter",
            condition_key="commit_count", condition_value=1,
            xp_reward=10, rarity="common",
        ),
    ]
    repo.get_user_achievements.return_value = []
    repo.get_counter.return_value = 0
    return repo


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def service(mock_repo, mock_event_bus):
    return GamificationService(repo=mock_repo, event_bus=mock_event_bus)


@pytest.mark.asyncio
class TestOnToolUsage:
    async def test_git_commit_awards_xp(self, service, mock_repo):
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Bash",
            tool_input={"command": "git commit -m 'feat: add feature'"},
        )
        await service.on_tool_usage(event)
        mock_repo.add_xp_log.assert_called_once()
        mock_repo.update_profile.assert_called()

    async def test_non_commit_bash_awards_nothing(self, service, mock_repo):
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Bash",
            tool_input={"command": "ls -la"},
        )
        await service.on_tool_usage(event)
        mock_repo.add_xp_log.assert_not_called()

    async def test_read_tool_awards_int_xp(self, service, mock_repo):
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Read",
            tool_input={"file_path": "/some/file.py"},
        )
        await service.on_tool_usage(event)
        mock_repo.add_xp_log.assert_called_once()
        call_args = mock_repo.add_xp_log.call_args[0][0]
        assert call_args.stat_type == "int"

    async def test_level_up_publishes_event(self, service, mock_repo, mock_event_bus):
        mock_repo.get_profile.return_value = RpgProfile(
            user_id=1, total_xp=95, level=1
        )
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Bash",
            tool_input={"command": "git commit -m 'feat: something'"},
        )
        await service.on_tool_usage(event)
        # After +30 XP (feat commit), total=125 -> level 2
        published_events = [
            call.args[0] for call in mock_event_bus.publish.call_args_list
        ]
        level_ups = [e for e in published_events if isinstance(e, LevelUpEvent)]
        assert len(level_ups) >= 1
