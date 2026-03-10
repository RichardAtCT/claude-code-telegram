"""Tests for gamification models."""

import pytest
from datetime import datetime, UTC

from src.gamification.models import (
    RpgProfile,
    XpLogEntry,
    AchievementDefinition,
    Achievement,
)


class TestRpgProfile:
    def test_default_values(self):
        profile = RpgProfile(user_id=123)
        assert profile.level == 1
        assert profile.total_xp == 0
        assert profile.str_points == 0
        assert profile.title == "Junior Developer"
        assert profile.current_streak == 0

    def test_to_dict(self):
        profile = RpgProfile(user_id=123, level=5, total_xp=1200)
        d = profile.to_dict()
        assert d["user_id"] == 123
        assert d["level"] == 5
        assert isinstance(d, dict)

    def test_from_row(self):
        row = {
            "user_id": 123, "level": 10, "total_xp": 5000,
            "str_points": 20, "int_points": 15, "dex_points": 10,
            "con_points": 18, "wis_points": 8,
            "current_streak": 7, "longest_streak": 14,
            "last_activity_date": "2026-03-10", "title": "Senior Developer",
        }
        profile = RpgProfile.from_row(row)
        assert profile.user_id == 123
        assert profile.level == 10
        assert profile.str_points == 20


class TestXpLogEntry:
    def test_creation(self):
        entry = XpLogEntry(
            user_id=123, xp_amount=10, source="commit",
            stat_type="str",
        )
        assert entry.xp_amount == 10
        assert entry.stat_type == "str"

    def test_to_dict_serializes_details(self):
        entry = XpLogEntry(
            user_id=123, xp_amount=10, source="commit",
            details={"files": ["a.py"]},
        )
        d = entry.to_dict()
        assert isinstance(d["details"], str)  # JSON string


class TestAchievementDefinition:
    def test_from_row(self):
        row = {
            "achievement_id": "first_blood", "name": "First Blood",
            "description": "Make your first commit", "icon": "",
            "category": "coding", "condition_type": "counter",
            "condition_key": "commit_count", "condition_value": 1,
            "xp_reward": 10, "rarity": "common", "is_active": True,
        }
        defn = AchievementDefinition.from_row(row)
        assert defn.achievement_id == "first_blood"
        assert defn.xp_reward == 10


class TestAchievement:
    def test_from_row(self):
        row = {
            "id": 1, "user_id": 123,
            "achievement_id": "first_blood",
            "unlocked_at": "2026-03-10T12:00:00",
            "data": None,
        }
        ach = Achievement.from_row(row)
        assert ach.achievement_id == "first_blood"
        assert isinstance(ach.unlocked_at, datetime)
